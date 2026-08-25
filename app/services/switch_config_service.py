# -*- coding: utf-8 -*-
"""
交换机端口配置服务（Facade）

提供 VLAN 配置、限速、端口聚合等操作的统一入口。
- 所有写入使用 send_config_commands（带重试），只读使用 get_connection。
- 统一入口：_execute_and_sync() 负责"发送 → 刷新缓存 → 广播事件"。
- 事务管理：由 _sync_port_from_device 统一 commit 与 SSE 事件发布，
  消除碎片化 DB 写入，确保最终一致性。

架构：SwitchConfigService 作为 Facade，将具体操作委托给子服务：
- VlanConfigService：VLAN 创建/删除/端口绑定
- LagConfigService：链路聚合创建/删除/成员管理
- PortClearService：端口配置清除
- BatchActionService：批量端口操作

依赖注入：子服务通过 CommandDispatcher 和 SyncCoordinator 访问共享能力，
不再持有 parent（Facade）反向引用，消除循环依赖。
"""
from app.utils.logging import get_logger
from contextlib import contextmanager
from typing import Optional

from app.adapters.adapter_factory import get_adapter
from app.infra import SSHManager
from app.persistence.switch_repo import SwitchRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.services.switch_event_schema import OpType
from app.services.device_op_lock import device_op_lock
from app.services.command_dispatcher import CommandDispatcher
from app.services.sync_coordinator import SyncCoordinator
from app.services.vlan_config_service import VlanConfigService
from app.services.lag_config_service import LagConfigService
from app.services.port_clear_service import PortClearService
from app.services.batch_action_service import BatchActionService
from app.utils.port_name_utils import is_vlan_interface

logger = get_logger(__name__)


class SwitchConfigService:
    """交换机端口配置服务（Facade）"""

    def __init__(self, ssh_manager: SSHManager = None):
        self.ssh_mgr = ssh_manager or SSHManager()
        self.port_repo = NetworkPortRepository()
        self.switch_repo = SwitchRepository()

        self._dispatcher = CommandDispatcher(self.ssh_mgr, device_op_lock)
        self._sync_coordinator = SyncCoordinator(self.ssh_mgr, self.switch_repo, device_op_lock)

        self._init_registry()

        self.clear_service = PortClearService(self._dispatcher, self.switch_repo, self._sync_coordinator, ssh_mgr=self.ssh_mgr)
        self.vlan_service = VlanConfigService(
            self._dispatcher, self.switch_repo, self._sync_coordinator,
            clear_service=self.clear_service,
        )
        self.lag_service = LagConfigService(
            self._dispatcher, self.switch_repo, self._sync_coordinator,
            clear_service=self.clear_service,
        )
        self.batch_service = BatchActionService(
            self._dispatcher, self.switch_repo, self._sync_coordinator,
            clear_service=self.clear_service,
            vlan_service=self.vlan_service,
            lag_service=self.lag_service,
            action_labels=self.ACTION_LABELS,
        )


    def _send_config(self, switch, commands: list, *,
                     ok_extra: dict = None,
                     err_label: str = "操作") -> dict:
        """发送配置命令：自动保存，CE 自动追加 commit（委托 CommandDispatcher）"""
        return self._dispatcher._send_config(switch, commands, ok_extra=ok_extra, err_label=err_label)

    def _send_config_no_save(self, switch, commands: list, *,
                             ok_extra: dict = None,
                             err_label: str = "操作") -> dict:
        """发送配置命令：不保存（委托 CommandDispatcher）"""
        return self._dispatcher._send_config_no_save(switch, commands, ok_extra=ok_extra, err_label=err_label)

    def _port_cmds(self, switch, port: str, *inner_cmds) -> list:
        """将命令包裹在 interface → <cmds> → quit 中（委托 CommandDispatcher）"""
        return self._dispatcher._port_cmds(switch, port, *inner_cmds)

    def _entity_exists(self, switch, check_cmd: str, entity_id: int,
                       entity_name: str = "VLAN/Trunk"):
        """通用的 VLAN/Trunk 存在性检查（委托 CommandDispatcher）

        Returns:
            Optional[bool]: True=存在, False=不存在, None=SSH检查失败
        """
        return self._dispatcher._entity_exists(switch, check_cmd, entity_id, entity_name)

    def _maybe_append_commit(self, commands: list, adapter, device_model: str) -> list:
        """华为 CE 系列需要在配置命令后追加 commit（委托 CommandDispatcher）"""
        return self._dispatcher._maybe_append_commit(commands, adapter, device_model)

    def save_config(self, switch) -> dict:
        """保存交换机配置（委托 CommandDispatcher）"""
        return self._dispatcher.save_config(switch)


    @contextmanager
    def _db_transaction(
        self,
        switch_id:            int,
        op_type:              str,
        *,
        affected_ports:       list[str] = None,
        affected_vlans:       list[int] = None,
        affected_lags:        list[int] = None,
        affected_connections: list[int] = None,
        extra:                dict      = None,
    ):
        """统一事务上下文（委托 SyncCoordinator）"""
        with self._sync_coordinator._db_transaction(
            switch_id, op_type,
            affected_ports=affected_ports,
            affected_vlans=affected_vlans,
            affected_lags=affected_lags,
            affected_connections=affected_connections,
            extra=extra,
        ):
            yield

    def _sync_port_from_device(self, switch_id: int, port: str,
                               op_type: str = OpType.PORT_UPDATE,
                               *,
                               affected_ports:  list[str] = None,
                               affected_vlans:  list[int] = None,
                               affected_lags:   list[int] = None,
                               affected_connections: list[int] = None) -> None:
        """SSH 配置成功后，从设备实时同步三表（委托 SyncCoordinator）"""
        self._sync_coordinator._sync_port_from_device(
            switch_id, port, op_type,
            affected_ports=affected_ports,
            affected_vlans=affected_vlans,
            affected_lags=affected_lags,
            affected_connections=affected_connections,
        )

    def fetch_port_config(
        self, device_id: int, port: str, force_refresh: bool = False,
    ) -> dict:
        """获取端口配置（委托 SyncCoordinator）"""
        return self._sync_coordinator.fetch_port_config(device_id, port, force_refresh=force_refresh)


    def _execute_and_sync(self, switch, port: str, commands: list, *,
                          op_type: str = OpType.PORT_UPDATE,
                          ok_extra: dict = None,
                          err_label: str = "操作",
                          affected_ports:  list[str] = None,
                          affected_vlans:  list[int] = None,
                          affected_lags:   list[int] = None,
                          affected_connections: list[int] = None) -> dict:
        """发送配置命令，成功后从设备同步三表并广播结构化 SSE 事件。

        绝大多数端口配置操作的统一出口，消除重复的
        `result = _send(); if success: _sync()` 模式。
        通过 device_op_lock 保证同一设备不会并发执行 SSH 操作。

        Args:
            switch:       交换机对象
            port:         端口名称
            commands:     待发送命令列表
            op_type:      SSE 事件操作类型（OpType 常量）
            ok_extra:     成功时附加到结果的额外字段
            err_label:    失败日志中的操作标签
            affected_ports:  变更的端口名列表
            affected_vlans:  变更的 VLAN 数据库 ID 列表
            affected_lags:   变更的 LAG 数据库 ID 列表
            affected_connections: 变更的连接 ID 列表

        Returns:
            dict: {success: bool, ...ok_extra}
        """
        with device_op_lock.acquire(switch.device_id):
            result = self._send_config(switch, commands, ok_extra=ok_extra,
                                      err_label=err_label)
            if result["success"]:
                self._sync_port_from_device(
                    switch.device_id, port, op_type,
                    affected_ports=affected_ports or [port],
                    affected_vlans=affected_vlans,
                    affected_lags=affected_lags,
                    affected_connections=affected_connections,
                )
        return result

    def _build_port_vlan_cmds(
        self, switch, port: str, vlan_id: int, mode: str,
        allowed_vlans: str = None,
    ) -> tuple[list, str]:
        """构造 VLAN 配置命令序列（委托 VlanConfigService）"""
        return self.vlan_service._build_port_vlan_cmds(switch, port, vlan_id, mode,
                                                        allowed_vlans=allowed_vlans)


    def configure_port_vlan(
        self, switch, port: str,
        vlan_id: int, vlan_type: str = "access",
    ) -> dict:
        """配置端口 VLAN（自动切换二/三层模式）

        Args:
            switch: 交换机对象
            port: 端口名称
            vlan_id: VLAN ID
            vlan_type: "access" 或 "trunk"

        Returns:
            dict: 配置结果
        """
        commands, _ = self._build_port_vlan_cmds(switch, port, vlan_id, vlan_type)
        with device_op_lock.acquire(switch.device_id):
            return self._send_config(
                switch, commands,
                ok_extra={"port": port, "vlan_id": vlan_id},
                err_label="配置端口 VLAN",
            )

    def configure_port_speed(self, switch, port: str, speed: str) -> dict:
        """配置端口协商速率（非 QoS 限速）"""
        return self._send_config(
            switch, self._port_cmds(switch, port, f"speed {speed}"),
            ok_extra={"port": port, "speed": speed},
            err_label="配置端口速率",
        )

    def shutdown_port(self, switch, port: str) -> dict:
        """关闭端口（单连接：config + save + 状态读取 + 配置同步）"""
        return self._single_enable_disable(switch, port, enable=False)

    def enable_port(self, switch, port: str) -> dict:
        """启用端口（单连接：config + save + 状态读取 + 配置同步）"""
        return self._single_enable_disable(switch, port, enable=True)

    def _single_enable_disable(self, switch, port: str, *, enable: bool) -> dict:
        """单端口启用/禁用：复用同一 SSH 连接完成全部操作，减少等待时间

        修复：启用/禁用后从设备读取**实际链路状态**写入 DB（而非硬编码 up/admin_down），
        保证前端开关状态与物理链路一致；并将配置缓存同步合并到同一连接，
        替代 _execute_and_sync 中「config 连接 + sync 连接」的多次 SSH 握手。

        流程：
        1. 建立 1 个 SSH 连接
        2. 下发 interface → undo shutdown/shutdown → quit（CE 追加 commit）
        3. 同一连接保存配置
        4. 同一连接读取实际链路状态 + 同步配置缓存（sync_single_port_on_conn）
        5. 广播 SSE

        Args:
            switch: 交换机对象
            port:   端口名称
            enable: True=启用（undo shutdown），False=禁用（shutdown）

        Returns:
            dict: {success, port, action}
        """
        action = "enable" if enable else "shutdown"
        err_label = "启用端口" if enable else "关闭端口"
        op_type = OpType.PORT_ENABLE if enable else OpType.PORT_DISABLE
        adapter = get_adapter(switch.device_type)
        inner_cmd = adapter.get_undo_shutdown_command() if enable else adapter.get_shutdown_command()
        commands = self._port_cmds(switch, port, inner_cmd)
        device_model = getattr(switch.device, "device_model", "") or ""
        commands = self._dispatcher._maybe_append_commit(commands, adapter, device_model)

        with device_op_lock.acquire(switch.device_id):
            try:
                with self.ssh_mgr.get_connection(switch) as conn:
                    self.ssh_mgr.execute_config_on_conn(conn, commands)
                    try:
                        self.ssh_mgr.execute_show_on_conn(
                            conn, adapter.get_save_command(device_model), timeout=60,
                        )
                    except Exception as e:
                        logger.warning("%s 保存配置失败（不影响操作结果）: %s", err_label, e)
                    self._sync_coordinator.sync_single_port_on_conn(
                        conn, switch, port, op_type,
                    )
            except Exception as e:
                logger.error("%s失败: %s", err_label, e)
                return {
                    "success": False, "error": self._dispatcher._classify_error(e),
                    "port": port, "action": action,
                }
        return {"success": True, "port": port, "action": action}

    def modify_port_description(self, switch, port: str, description: str) -> dict:
        """修改或删除端口描述

        description 非空时设置描述，为空时删除描述配置。
        成功后同步更新数据库中的描述字段。
        """
        a = get_adapter(switch.device_type)
        inner_cmd = (
            a.get_description_command(description) if description
            else a.get_undo_description_command()
        )
        with device_op_lock.acquire(switch.device_id):
            result = self._send_config(
                switch, self._port_cmds(switch, port, inner_cmd),
                ok_extra={"message": f"端口 {port} 描述已{'更新' if description else '删除'}"},
                err_label="修改端口描述",
            )
        if result["success"]:
            self._sync_port_from_device(switch.device_id, port)
        return result


    _DISPATCH_REGISTRY: dict[str, tuple] = {}

    @classmethod
    def _init_registry(cls):
        """初始化操作注册表（幂等：仅在注册表为空时执行）

        避免每次实例化都重新赋值类级别字典，
        防止多实例场景下相互覆盖。
        """
        if cls._DISPATCH_REGISTRY:
            return
        cls._DISPATCH_REGISTRY = {
            'enable_port':            (cls._handle_enable_port,            '启用端口',     OpType.PORT_ENABLE),
            'disable_port':           (cls._handle_disable_port,           '关闭端口',     OpType.PORT_DISABLE),
            'update_port_info':       (cls._handle_update_port_info,       '修改端口信息', OpType.PORT_UPDATE),
            'assign_customer':        (cls._handle_assign_customer,        '分配客户',     OpType.PORT_UPDATE),
            'set_port_speed':         (cls._handle_set_port_speed,         '设置端口限速', OpType.PORT_SPEED_LIMIT),
            'set_port_vlan':          (cls._handle_set_port_vlan,          '配置端口VLAN', OpType.PORT_VLAN_CONFIG),
            'set_port_ip':            (cls._handle_set_port_ip,            '配置端口IP',   OpType.PORT_IP_SET),
            'delete_port_ip':         (cls._handle_delete_port_ip,         '删除端口IP',   OpType.PORT_IP_SET),
            'clear_port_config':      (cls._handle_clear_port_config,      '清除端口配置', OpType.PORT_UPDATE),
            'delete_interface':       (cls._handle_delete_interface,       '删除接口',     OpType.PORT_DELETE),
            'add_port_to_trunk':      (cls._handle_add_port_to_trunk,      '加入链路聚合', OpType.LAG_MEMBER_SET),
            'delete_trunk':           (cls._handle_delete_trunk,           '删除链路聚合', OpType.LAG_DELETE),
            'create_port_channel':    (cls._handle_create_port_channel,    '创建链路聚合', OpType.LAG_CREATE),
            'remove_port_from_channel': (cls._handle_remove_port_from_channel, '移除链路聚合成员', OpType.LAG_MEMBER_SET),
            'delete_vlan':            (cls._handle_delete_vlan,            '删除VLAN',     OpType.VLAN_DELETE),
        }

    @property
    def ACTION_LABELS(self) -> dict:
        """action → 中文标签（从注册表派生）"""
        return {action: entry[1] for action, entry in self._DISPATCH_REGISTRY.items()}

    @property
    def ACTION_OP_TYPE_MAP(self) -> dict:
        """action → op_type 映射（从注册表派生，供前端精确缓存失效）"""
        return {action: entry[2] for action, entry in self._DISPATCH_REGISTRY.items()}


    def _handle_enable_port(self, switch, port: str, params: dict) -> dict:
        """启用端口"""
        return self.enable_port(switch, port)

    def _handle_disable_port(self, switch, port: str, params: dict) -> dict:
        """关闭端口"""
        return self.shutdown_port(switch, port)

    def _handle_update_port_info(self, switch, port: str, params: dict) -> dict:
        """修改端口信息"""
        description = params.get("description", "")
        return self.modify_port_description(switch, port, description)

    def _handle_assign_customer(self, switch, port: str, params: dict) -> dict:
        """分配客户（仅更新数据库，不需要SSH命令）"""
        customer_id = params.get("customer_id")
        self.switch_repo.update_port_customer(switch.device_id, port, customer_id)
        return {"success": True, "port": port}

    def _handle_set_port_speed(self, switch, port: str, params: dict) -> dict:
        """设置端口限速"""
        inbound = params.get("inbound_speed", 0)
        outbound = params.get("outbound_speed", 0)
        return self.set_port_speed_limit(switch, port, inbound, outbound)

    def _handle_set_port_vlan(self, switch, port: str, params: dict) -> dict:
        """配置端口VLAN"""
        vlan_id = params.get("vlan_id")
        mode = params.get("mode", "access")
        allowed_vlans = params.get("allowed_vlans")
        return self.set_port_vlan(switch, port, vlan_id, mode, allowed_vlans=allowed_vlans)

    def _handle_set_port_ip(self, switch, port: str, params: dict) -> dict:
        """配置端口IP"""
        ip_address = params.get("ip_address")
        subnet_mask = params.get("subnet_mask")
        is_secondary = params.get("is_secondary", False)
        return self.set_port_ip(switch, port, ip_address, subnet_mask, is_secondary)

    def _handle_delete_port_ip(self, switch, port: str, params: dict) -> dict:
        """删除端口IP"""
        ip_address = params.get("ip_address")
        subnet_mask = params.get("subnet_mask")
        is_secondary = params.get("is_secondary", False)
        return self.delete_port_ip(switch, port, ip_address, subnet_mask, is_secondary)

    def _handle_clear_port_config(self, switch, port: str, params: dict) -> dict:
        """清除端口配置"""
        return self.clear_port_config(switch, port)

    def _handle_delete_interface(self, switch, port: str, params: dict) -> dict:
        """删除接口"""
        return self.delete_interface(switch, port)

    def _handle_add_port_to_trunk(self, switch, port: str, params: dict) -> dict:
        """加入链路聚合"""
        channel_id = params.get("channel_id")
        return self.add_port_to_channel(switch, channel_id, port)

    def _handle_delete_trunk(self, switch, port: str, params: dict) -> dict:
        """删除链路聚合"""
        trunk_id = params.get("trunk_id")
        return self.delete_eth_trunk(switch, trunk_id)

    def _handle_create_port_channel(self, switch, port: str, params: dict) -> dict:
        """创建链路聚合"""
        channel_id = params.get("channel_id")
        member_ports = params.get("member_ports", [])
        return self.create_port_channel(switch, channel_id, member_ports)

    def _handle_remove_port_from_channel(self, switch, port: str, params: dict) -> dict:
        """移除链路聚合成员"""
        return self.remove_port_from_channel(switch, port)

    def _handle_delete_vlan(self, switch, port: str, params: dict) -> dict:
        """删除VLAN"""
        vlan_id = params.get("vlan_id")
        return self.delete_vlan(switch, vlan_id)

    def dispatch_port_action(self, switch, action: str, port: str,
                             params: dict = None) -> dict:
        """根据操作类型分发到对应的配置方法（注册表模式）

        Args:
            switch: 交换机对象
            action: 操作类型（如 enable_port / set_port_vlan）
            port:   端口名称
            params: 操作参数字典

        Returns:
            dict: {success: bool, message?: str, error?: str}
        """
        entry = self._DISPATCH_REGISTRY.get(action)
        if not entry:
            return {"success": False, "error": f"不支持的操作类型: {action}"}

        handler, label, op_type = entry
        try:
            result = handler(self, switch, port, params or {})
            if result.get("success") and not result.get("message"):
                result["message"] = f"{label}成功"
            result.setdefault("detail_op_type", op_type)
            return result
        except Exception as e:
            logger.error("%s异常: %s", label, e, exc_info=True)
            return {"success": False, "error": str(e)}


    _SSH_ONLY_ACTIONS = frozenset({
        'set_port_speed',        # QoS策略需设备下发
        'cancel_port_speed',     # 同上
        'set_port_ip',           # IP配置需设备下发
        'delete_port_ip',        # 同上
        'delete_interface',      # 删除虚拟接口需设备执行
        'delete_trunk',          # 删除Eth-Trunk需设备执行
        'delete_vlan',           # 删除VLAN需设备下发
        'create_port_channel',   # 创建Eth-Trunk需设备执行
    })

    def dispatch_port_action_db(self, device_id: int, action: str,
                                 port: str, params: dict = None) -> dict:
        """单端口操作（非网管设备，直接操作数据库）

        对齐 BatchActionService.batch_port_action_db 的单端口等价逻辑。
        SSH-only 操作直接返回不支持错误。

        Args:
            device_id: 交换机 device_id
            action: 操作类型
            port: 端口名称
            params: 操作参数

        Returns:
            dict: {success: bool, message?: str, error?: str}
        """
        params = params or {}
        op_type = self.ACTION_OP_TYPE_MAP.get(action, OpType.PORT_UPDATE)

        if action in self._SSH_ONLY_ACTIONS:
            label = self.ACTION_LABELS.get(action, action)
            return {
                "success": False,
                "error": f"非网管设备不支持{label}操作（需SSH连接设备）",
            }

        port_row = self.switch_repo.find_port_by_device_and_name(device_id, port)
        if not port_row:
            return {"success": False, "error": f"端口 {port} 不存在"}

        try:
            with self._db_transaction(device_id, op_type, affected_ports=[port]):
                if action == 'enable_port':
                    port_row.link_status = 'up'
                    port_row.usage_status = 'free'
                elif action == 'disable_port':
                    port_row.link_status = 'admin_down'
                    port_row.usage_status = 'disabled'
                elif action == 'set_port_vlan':
                    vlan_id = params.get('vlan_id')
                    port_row.vlan = str(vlan_id) if vlan_id else None
                elif action == 'update_port_info':
                    description = params.get('description', '')
                    port_row.description = description
                elif action == 'assign_customer':
                    customer_id = params.get('customer_id')
                    port_row.customer_id = customer_id
                elif action == 'add_port_to_trunk':
                    channel_id = params.get('channel_id')
                    sc = self.switch_repo.find_by_device_id(device_id)
                    dt = sc.device_type if sc else None
                    self.lag_service._update_lag_member_relation(
                        device_id, port, channel_id, device_type=dt
                    )
                elif action == 'remove_port_from_channel':
                    self.lag_service._clear_lag_member_relation(device_id, port)
                elif action == 'clear_port_config':
                    port_row.vlan = None
                    port_row.description = None
                    port_row.link_status = 'up'
                    port_row.usage_status = 'free'
                    self.lag_service._clear_lag_member_relation(device_id, port)
                else:
                    return {"success": False, "error": f"不支持的操作类型: {action}"}

            label = self.ACTION_LABELS.get(action, action)
            return {"success": True, "message": f"{label}成功"}
        except Exception as e:
            logger.error("非网管设备端口操作失败 device=%d port=%s action=%s: %s",
                         device_id, port, action, e, exc_info=True)
            return {"success": False, "error": str(e)}


    def _clear_port_config_on_device(self, switch, port: str,
                                     auto_save: bool = True) -> dict:
        """在设备上清除端口配置（委托 PortClearService）"""
        return self.clear_service._clear_port_config_on_device(switch, port, auto_save=auto_save)

    def clear_port_config(self, switch, port: str) -> dict:
        """清除端口配置（SSH 清除 + 从设备同步三表）

        在设备上执行 clear configuration interface <port>，
        成功后通过 _sync_port_from_device 从设备实时读取配置并同步三表，
        避免手动 DB 清空与 refresh 重复。
        """
        result = self._clear_port_config_on_device(switch, port)
        if result["success"]:
            self._sync_port_from_device(switch.device_id, port, OpType.PORT_UPDATE)
            result["message"] = f"端口 {port} 配置已清除"
        return result

    def _batch_clear_ports(self, switch, ports: list[str],
                           auto_save: bool = True) -> None:
        """批量清除端口配置（委托 PortClearService）"""
        self.clear_service._batch_clear_ports(switch, ports, auto_save=auto_save)

    def _get_port_members(self, switch, port: str, port_type: str) -> list:
        """获取 VLANIF 或 Eth-Trunk 的成员端口列表（委托 SyncCoordinator）"""
        return self._sync_coordinator._get_port_members(switch, port, port_type)


    def create_vlan(self, switch, vlan_id: int) -> dict:
        """创建 VLAN（委托 VlanConfigService）"""
        return self.vlan_service.create_vlan(switch, vlan_id)

    def delete_vlan(self, switch, vlan_id: int) -> dict:
        """删除 VLAN（委托 VlanConfigService）"""
        return self.vlan_service.delete_vlan(switch, vlan_id)

    def set_port_vlan(self, switch, port: str, vlan_id: int,
                      mode: str = "access", allowed_vlans: str = None) -> dict:
        """设置端口 VLAN（委托 VlanConfigService）"""
        return self.vlan_service.set_port_vlan(switch, port, vlan_id, mode, allowed_vlans=allowed_vlans)


    def create_port_channel(self, switch, channel_id: int, member_ports: list) -> dict:
        """创建链路聚合（委托 LagConfigService）"""
        return self.lag_service.create_port_channel(switch, channel_id, member_ports)

    def delete_eth_trunk(self, switch, trunk_id: int) -> dict:
        """删除 Eth-Trunk（委托 LagConfigService）"""
        return self.lag_service.delete_eth_trunk(switch, trunk_id)

    def add_port_to_channel(self, switch, channel_id: int, port: str) -> dict:
        """添加端口到链路聚合（委托 LagConfigService）"""
        return self.lag_service.add_port_to_channel(switch, channel_id, port)

    def remove_port_from_channel(self, switch, port: str) -> dict:
        """从链路聚合组移除端口（委托 LagConfigService）"""
        return self.lag_service.remove_port_from_channel(switch, port)

    def delete_interface(self, switch, port: str) -> dict:
        """删除接口（LoopBack等虚拟接口），并清理 switch_port_status 中对应记录"""
        adapter = get_adapter(switch.device_type)
        commands = [adapter.get_delete_interface_command(port)]
        result = self._send_config(
            switch, commands,
            ok_extra={"message": f"接口 {port} 已删除"},
            err_label="删除接口",
        )
        if result["success"]:
            with self._db_transaction(switch.device_id, OpType.PORT_DELETE,
                                      affected_ports=[port]):
                self.switch_repo.delete_vlan_trunk_info(switch.device_id, port)
                self.switch_repo.delete_port_config(switch.device_id, port)
        return result


    def set_port_speed_limit(
        self, switch, port: str, inbound: int, outbound: int,
    ) -> dict:
        """设置端口限速（QoS 策略方式）

        统一使用 traffic-policy（华为）或 qos policy（H3C）方式限速。
        先从设备读取当前接口配置，提取已应用的策略名并撤销，
        再创建并应用新策略（0 表示仅取消限速）。

        Args:
            switch: 交换机对象
            port: 端口名称
            inbound: 上行限速（Mbps），0 = 取消限速
            outbound: 下行限速（Mbps），0 = 取消限速

        Returns:
            dict: 操作结果
        """
        a = get_adapter(switch.device_type)
        commands = []

        has_cancel = any((s is None or s <= 0) for s in (inbound, outbound))
        existing_policies = self._get_applied_qos_policies(switch, port) if has_cancel else []

        for direction, speed in (("inbound", inbound), ("outbound", outbound)):
            if speed is None or speed <= 0:
                for policy_name, d in existing_policies:
                    if d == direction:
                        commands.append(a.get_enter_interface_command(port))
                        commands.append(a.get_undo_apply_qos_policy_command(direction, policy_name))
                        commands.append(a.get_exit_interface_command())
                continue

            policy_name = a.get_qos_policy_name(direction, speed)
            cir_kbps = speed * 1000
            if not self._qos_policy_exists_on_device(switch, a, policy_name):
                commands.extend(a.get_create_qos_policy_commands(policy_name, cir_kbps))
            commands.append(a.get_enter_interface_command(port))
            commands.append(a.get_apply_qos_policy_command(policy_name, direction))
            commands.append(a.get_exit_interface_command())

        return self._execute_and_sync(
            switch, port, commands,
            op_type=OpType.PORT_SPEED_LIMIT,
            ok_extra={"message": f"端口 {port} 限速已设置", "inbound": inbound, "outbound": outbound},
            err_label="设置端口限速",
        )


    def modify_route_ip(self, switch, network_ip: str, mask: str, nexthop: str) -> dict:
        """删除一条静态路由"""
        adapter = get_adapter(switch.device_type)
        commands = [adapter.get_delete_route_command(network_ip, mask, nexthop)]
        return self._send_config(switch, commands, ok_extra={"message": "路由已修改"}, err_label="修改路由IP配置")

    def set_port_ip(
        self, switch, port: str, ip_address: str, subnet_mask: str,
        is_secondary: bool = False,
    ) -> dict:
        """设置端口 IP 地址（三层模式，VLANIF 接口跳过 undo portswitch）

        若端口属于 Eth-Trunk，拒绝操作并提示用户先退出 Trunk。
        SSH 成功后统一通过 _sync_port_from_device 从设备同步三表。
        """
        trunk_id = self._get_port_trunk_id(switch.device_id, port)
        if trunk_id is not None:
            return {
                "success": False,
                "error": f"端口 {port} 属于 Eth-Trunk {trunk_id}，请先退出 Eth-Trunk（点击端口详情 → 清除配置），或在 Eth-Trunk {trunk_id} 上配置 IP",
            }

        current_vlan = self.switch_repo.get_port_vlan(switch.device_id, port)
        if current_vlan is not None and current_vlan != 1:
            return {
                "success": False,
                "error": f"端口 {port} 属于 VLAN {current_vlan}，不能直接配置 IP。请先在 VLAN 1 或三层接口上配置 IP。",
            }

        conflict = self.switch_repo.check_ip_subnet_conflict(
            switch.device_id, ip_address, subnet_mask, port,
        )
        if conflict:
            return {
                "success": False,
                "error": f"IP 网段 {ip_address}/{subnet_mask} 与端口 {conflict['port']} 的 {conflict['ip']}（网段 {conflict['subnet']}）重叠，同一交换机上同一网段只能分配一次。",
            }

        a = get_adapter(switch.device_type)
        is_vlanif = is_vlan_interface(port)
        need_mode_switch = current_vlan is not None and not is_vlanif
        mode_cmd = a.get_undo_portswitch_command() if need_mode_switch else ""

        ip_cmd = (
            a.get_set_secondary_ip_command(ip_address, subnet_mask)
            if is_secondary
            else a.get_set_ip_command(ip_address, subnet_mask)
        )
        inner = [ip_cmd] if not mode_cmd else [mode_cmd, ip_cmd]

        result = self._send_config(switch, self._port_cmds(switch, port, *inner), err_label="设置端口IP")
        if result["success"]:
            result["message"] = f"端口 {port} IP已设置"
            self._sync_port_from_device(switch.device_id, port, OpType.PORT_IP_SET)
        return result

    def delete_port_ip(self, switch, port: str, ip_address: str, subnet_mask: str, is_secondary: bool = False) -> dict:
        """删除端口 IP 地址

        Args:
            is_secondary: 是否为从IP，从IP删除命令需加sub/secondary关键字

        SSH 成功后统一通过 _sync_port_from_device 从设备同步三表。
        """
        a = get_adapter(switch.device_type)
        return self._execute_and_sync(
            switch, port,
            self._port_cmds(switch, port, a.get_undo_ip_command(ip_address, subnet_mask, is_secondary)),
            op_type=OpType.PORT_IP_SET,
            err_label="删除端口IP",
        )

    def get_port_ips(self, device_id: int, port: str) -> list:
        """查询端口 IP 列表

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）
        """
        return self.switch_repo.get_port_ips(device_id, port)

    def update_port_customer(self, device_id: int, port: str, customer_id: int) -> dict:
        """更新端口客户归属

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）
        """
        if customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(customer_id)
        with self._db_transaction(device_id, OpType.PORT_UPDATE,
                                  affected_ports=[port]):
            self.switch_repo.update_port_customer(device_id, port, customer_id)
        return {"success": True, "message": "客户归属已更新"}

    def get_cached_port_detail(self, device_id: int, port: str):
        """获取缓存端口详情（从 switch_port_status 表读取）

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）
        """
        return self.switch_repo.get_port_info_cache(device_id, port)


    def _get_cached_config(self, switch_id: int, port: str) -> Optional[dict]:
        """从缓存中提取端口配置（委托 SyncCoordinator）"""
        return self._sync_coordinator._get_cached_config(switch_id, port)

    def _get_port_trunk_id(self, switch_id: int, port: str) -> Optional[int]:
        """从配置缓存中解析端口所属的 Eth-Trunk ID

        委托适配器解析设备回显格式，遵循 OCP 原则。

        Args:
            switch_id: 交换机 ID
            port:      端口名称

        Returns:
            Eth-Trunk ID（如 10），不属于任何 Trunk 时返回 None
        """
        config_text = self.switch_repo.get_port_config_text(switch_id, port)
        if not config_text:
            return None

        switch = self.switch_repo.find_by_device_id(switch_id)
        if not switch:
            return None
        adapter = get_adapter(switch.device_type)
        return adapter.parse_trunk_id(config_text)

    def _sync_trunk_members(self, device_id: int, port: str, members: list) -> None:
        """将Eth-Trunk成员端口列表写入link_aggregation_groups表（委托 SyncCoordinator）"""
        self._sync_coordinator._sync_trunk_members(device_id, port, members)

    def _sync_port_vlan_from_config(
        self, switch_id: int, port: str, config_text: str, adapter=None,
    ) -> None:
        """从端口配置文本提取 VLAN ID，同步回 switch_port_status.vlan（委托 SyncCoordinator）"""
        self._sync_coordinator._sync_port_vlan_from_config(switch_id, port, config_text, adapter)

    def _sync_port_ips_from_config(
        self, switch_id: int, port: str, config_text: str, adapter,
    ) -> None:
        """从端口配置文本提取 IP，全量同步到 switch_port_ips（委托 SyncCoordinator）"""
        self._sync_coordinator._sync_port_ips_from_config(switch_id, port, config_text, adapter)

    def _sync_port_description_from_config(
        self, switch_id: int, port: str, config_text: str, adapter=None,
    ) -> None:
        """从端口配置文本提取描述，同步回 switch_port_status.description（委托 SyncCoordinator）"""
        self._sync_coordinator._sync_port_description_from_config(switch_id, port, config_text, adapter)

    def _qos_policy_exists_on_device(self, switch, adapter, policy_name: str) -> bool:
        """查询设备上是否已存在指定 QoS 策略（限速策略去重）

        已存在则上层跳过创建、直接引用。查询失败（超时/异常/无回显）时保守返回
        False 触发创建——重定义相同内容的策略在华为/H3C 上是幂等的，不会破坏
        其它已引用该策略的端口。

        Returns:
            bool: True 表示策略已存在
        """
        try:
            output = self.ssh_mgr.send_show_command(
                switch, adapter.get_qos_policy_query_command(policy_name),
            )
        except Exception as e:
            logger.warning("查询QoS策略 %s 是否存在失败: %s", policy_name, e)
            return False
        if not output:
            return False
        return not adapter.is_qos_policy_missing(output)

    def _get_applied_qos_policies(self, switch, port: str) -> list:
        """从设备读取当前接口配置，提取已应用的 QoS 策略名和方向

        委托适配器解析设备回显格式，遵循 OCP 原则。

        Returns:
            list[tuple[str, str]]: [(policy_name, direction), ...]
        """
        try:
            config_output = self.ssh_mgr.send_show_command(
                switch, f"display current-configuration interface {port}",
            )
            if not config_output:
                return []
            adapter = get_adapter(switch.device_type)
            return adapter.parse_qos_policies(config_output)
        except Exception as e:
            logger.warning("读取端口 %s 已应用QoS策略失败: %s", port, e)
            return []


    def batch_port_action(self, switch, action: str, ports: list[str],
                          params: dict = None) -> dict:
        """批量端口操作（网管交换机，委托 BatchActionService）"""
        return self.batch_service.batch_port_action(switch, action, ports, params)

    def batch_port_action_db(self, device_id: int, action: str,
                             ports: list[str], params: dict = None) -> dict:
        """批量端口操作（非网管交换机，委托 BatchActionService）"""
        return self.batch_service.batch_port_action_db(device_id, action, ports, params)