# -*- coding: utf-8 -*-
"""
批量操作子服务

从 SwitchConfigService 拆分出的批量端口操作：
- batch_port_action / batch_port_action_db
- _build_batch_inner_cmds / _build_batch_vlan_cmds / _build_port_expr
- _CLEAR_FIRST_ACTIONS / _BATCH_OP_TYPE_MAP
"""
from app.utils.logging import get_logger
from typing import Optional

from app.adapters.adapter_factory import get_adapter
from app.persistence.switch_repo import SwitchRepository
from app.services.switch_event_schema import OpType
from app.services.device_op_lock import device_op_lock
from app.utils.port_name_utils import get_trunk_name, normalize_port

logger = get_logger(__name__)

class BatchActionService:
    """批量操作子服务"""

    _CLEAR_FIRST_ACTIONS = {"set_port_vlan", "add_port_to_trunk"}

    _BATCH_OP_TYPE_MAP = {
        "enable_port": OpType.PORT_ENABLE,
        "disable_port": OpType.PORT_DISABLE,
        "set_port_vlan": OpType.PORT_VLAN_CONFIG,
        "update_port_info": OpType.PORT_UPDATE,
        "assign_customer": OpType.PORT_UPDATE,
        "add_port_to_trunk": OpType.LAG_MEMBER_SET,
        "remove_port_from_channel": OpType.LAG_MEMBER_SET,
        "clear_port_config": OpType.PORT_CLEAR_CONFIG,
        "set_port_speed": OpType.PORT_SPEED_LIMIT,
        "cancel_port_speed": OpType.PORT_SPEED_LIMIT,
    }

    def __init__(self, dispatcher, switch_repo: SwitchRepository, sync_coordinator,
                 clear_service=None, vlan_service=None, lag_service=None,
                 action_labels: dict = None):
        """
        Args:
            dispatcher: CommandDispatcher 实例，用于命令下发
            switch_repo: SwitchRepository 实例
            sync_coordinator: SyncCoordinator 实例，用于事务与同步
            clear_service: PortClearService 实例，用于端口清除
            vlan_service: VlanConfigService 实例，用于 VLAN 操作
            lag_service: LagConfigService 实例，用于 LAG 操作
            action_labels: 操作标签映射（从 Facade 的 ACTION_LABELS 传入）
        """
        self.dispatcher = dispatcher
        self.switch_repo = switch_repo
        self.sync = sync_coordinator
        self.clear_service = clear_service
        self.vlan_service = vlan_service
        self.lag_service = lag_service
        self._action_labels = action_labels or {}

    def batch_port_action(self, switch, action: str, ports: list[str],
                          params: dict = None) -> dict:
        """批量端口操作（网管交换机，通过 interface range 命令）

        流程：
        1. 获取设备操作锁
        2. 对 set_port_vlan / add_port_to_trunk：先逐端口 clear configuration
        3. 构造 interface range 命令 + 配置命令
        4. SSH 下发（关闭自动保存）
        5. 统一保存配置
        6. 逐端口 _sync_port_from_device 同步三表
        7. 返回每个端口的操作结果

        Args:
            switch: 交换机对象（SwitchCredentials）
            action: 操作类型
            ports: 端口名称列表（已展开、去重）
            params: 操作参数

        Returns:
            dict: {total, succeeded, failed, details: [{port, success, error?}]}
        """
        params = params or {}
        op_type = self._BATCH_OP_TYPE_MAP.get(action, OpType.PORT_UPDATE)
        adapter = get_adapter(switch.device_type)
        details = []

        with device_op_lock.acquire(switch.device_id):
            if action in self._CLEAR_FIRST_ACTIONS:
                self.clear_service._batch_clear_ports(switch, ports, auto_save=False)

            if action == "set_port_vlan":
                vlan_id = params.get("vlan_id")
                mode = params.get("mode", "access")
                vlan_result = self.vlan_service.create_vlan(switch, vlan_id)
                if not vlan_result.get("success"):
                    return {
                        "success": False,
                        "error": f"VLAN {vlan_id} 自动创建失败: {vlan_result.get('error', '')}",
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False, "error": f"VLAN {vlan_id} 创建失败"} for p in ports],
                    }
                if mode == "trunk":
                    allowed_vlans = params.get("allowed_vlans")
                    if allowed_vlans:
                        from app.adapters.base_adapter import BaseDeviceAdapter
                        vlan_ranges = BaseDeviceAdapter.parse_vlan_ranges(allowed_vlans)
                        for start, end in vlan_ranges:
                            for vid in range(start, end + 1):
                                if vid == vlan_id:
                                    continue
                                self.vlan_service.create_vlan(switch, vid)

            elif action == "add_port_to_trunk":
                channel_id = params.get("channel_id")
                trunk_result = self.lag_service._ensure_trunk_exists(switch, channel_id)
                if not trunk_result.get("success"):
                    return {
                        "success": False,
                        "error": f"Eth-Trunk {channel_id} 自动创建失败: {trunk_result.get('error', '')}",
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False, "error": f"Eth-Trunk {channel_id} 创建失败"} for p in ports],
                    }

            if action == "clear_port_config":
                self.clear_service._batch_clear_ports(switch, ports, auto_save=True)
                sync_res = self.sync.bulk_sync_ports_from_device(switch.device_id, ports, op_type)
                for port in sync_res["succeeded"]:
                    self.lag_service._clear_lag_member_relation(switch.device_id, port)
                    details.append({"port": port, "success": True})
                for port, reason in sync_res["failed"]:
                    details.append({"port": port, "success": False, "error": reason})
                succeeded = sum(1 for d in details if d["success"])
                return {
                    "success": succeeded > 0,
                    "total": len(ports),
                    "succeeded": succeeded,
                    "failed": len(ports) - succeeded,
                    "details": details,
                }

            if action == "assign_customer":
                customer_id = params.get("customer_id")
                with self.sync._db_transaction(switch.device_id, op_type,
                                                affected_ports=ports):
                    for port in ports:
                        sp = self.switch_repo.session.begin_nested()
                        try:
                            port_row = self.switch_repo.find_port_by_device_and_name(switch.device_id, port)
                            if port_row:
                                port_row.customer_id = customer_id
                                details.append({"port": port, "success": True})
                            else:
                                sp.rollback()
                                details.append({"port": port, "success": False, "error": "端口不存在"})
                        except Exception as e:
                            sp.rollback()
                            logger.warning("批量分配客户端口 %s 失败: %s", port, e)
                            details.append({"port": port, "success": False, "error": str(e)})
                succeeded = sum(1 for d in details if d["success"])
                return {
                    "success": succeeded > 0,
                    "total": len(ports),
                    "succeeded": succeeded,
                    "failed": len(ports) - succeeded,
                    "details": details,
                }

            if action == "add_port_to_trunk":
                channel_id = params.get("channel_id")
                trunk_name = get_trunk_name(switch.device_type, channel_id)
                if hasattr(adapter, 'get_trunkport_command'):
                    from app.utils.port_range_parser import PortRangeParser
                    try:
                        trunkport_expr = PortRangeParser.build_trunkport_expr(ports)
                    except ValueError as e:
                        logger.warning("构建 trunkport 表达式失败，跳过: %s", e)
                        return {
                            "success": False, "error": str(e),
                            "total": len(ports), "succeeded": 0, "failed": len(ports),
                            "details": [{"port": p, "success": False, "error": str(e)} for p in ports],
                        }
                    trunkport_lines = [line.strip() for line in trunkport_expr.split("\n") if line.strip()]
                    commands = [adapter.get_enter_interface_command(trunk_name)]
                    for line in trunkport_lines:
                        commands.append(adapter.get_trunkport_command(line))
                    commands.append(adapter.get_exit_interface_command())
                else:
                    add_cmd = adapter.get_add_member_command(channel_id)
                    commands = []
                    for port in ports:
                        commands.extend(self.dispatcher._port_cmds(switch, port, add_cmd))
                result = self.dispatcher._send_config_no_save(
                    switch, commands,
                    err_label="批量加入链路聚合",
                    read_timeout=max(120, len(ports) * 3),
                )
                if not result["success"]:
                    return {
                        "success": False, "error": result.get("error", "SSH命令执行失败"),
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False, "error": result.get("error", "")} for p in ports],
                    }
                try:
                    self.dispatcher.save_config(switch)
                except Exception as e:
                    logger.warning("批量加入Trunk后保存配置失败: %s", e)
                sync_res = self.sync.bulk_sync_ports_from_device(switch.device_id, ports, op_type)
                for port in sync_res["succeeded"]:
                    self.lag_service._update_lag_member_relation(switch.device_id, port, channel_id, device_type=switch.device_type)
                    details.append({"port": port, "success": True})
                for port, reason in sync_res["failed"]:
                    details.append({"port": port, "success": False, "error": reason})
                succeeded = sum(1 for d in details if d["success"])
                return {
                    "success": succeeded > 0,
                    "total": len(ports),
                    "succeeded": succeeded,
                    "failed": len(ports) - succeeded,
                    "details": details,
                }

            if action == "set_port_speed":
                inbound = self._coerce_speed(params.get("inbound"))
                outbound = self._coerce_speed(params.get("outbound"))
                directions = []
                for direction, speed in (("inbound", inbound), ("outbound", outbound)):
                    if speed is not None:
                        directions.append((direction, speed))
                if not directions:
                    return {
                        "success": False,
                        "error": "未提供有效的限速值（inbound/outbound 需为大于 0 的数值）",
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False,
                                     "error": "未提供有效的限速值"} for p in ports],
                    }
                create_cmds = []
                for direction, speed in directions:
                    policy_name = adapter.get_qos_policy_name(direction, speed)
                    if not self._qos_policy_exists_on_device(switch, adapter, policy_name):
                        create_cmds.extend(
                            adapter.get_create_qos_policy_commands(policy_name, speed * 1000)
                        )
                apply_cmds = []
                for direction, speed in directions:
                    policy_name = adapter.get_qos_policy_name(direction, speed)
                    apply_cmds.append(adapter.get_apply_qos_policy_command(policy_name, direction))
                port_expr = self._build_port_expr(ports, switch.device_type)
                range_commands = [
                    *create_cmds,
                    adapter.get_interface_range_command(port_expr),
                    *apply_cmds,
                    adapter.get_exit_interface_command(),
                ]

                def _build_pp():
                    return self._build_per_port_commands(
                        adapter, ports, apply_cmds, prefix_cmds=create_cmds,
                    )

                result, _mode = self._send_with_range_fallback(
                    switch, len(ports), range_commands, _build_pp,
                    err_label=f"批量{self._action_labels.get(action, action)}",
                    read_timeout=max(120, len(ports) * 3),
                )
                if not result["success"]:
                    return {
                        "success": False, "error": result.get("error", "SSH命令执行失败"),
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False,
                                     "error": result.get("error", "")} for p in ports],
                    }
                try:
                    self.dispatcher.save_config(switch)
                except Exception as e:
                    logger.warning("批量限速后统一保存配置失败: %s", e)
                sync_res = self.sync.bulk_sync_ports_from_device(switch.device_id, ports, op_type)
                for port in sync_res["succeeded"]:
                    details.append({"port": port, "success": True})
                for port, reason in sync_res["failed"]:
                    details.append({"port": port, "success": False, "error": reason})
                succeeded = sum(1 for d in details if d["success"])
                return {
                    "success": succeeded > 0,
                    "total": len(ports), "succeeded": succeeded,
                    "failed": len(ports) - succeeded, "details": details,
                }

            if action == "cancel_port_speed":
                cancel_inbound = bool(params.get("cancel_inbound", True))
                cancel_outbound = bool(params.get("cancel_outbound", True))
                if not (cancel_inbound or cancel_outbound):
                    return {
                        "success": False, "error": "请至少选择取消入向或出向限速",
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False,
                                     "error": "未选择取消方向"} for p in ports],
                    }
                cancel_dirs = set()
                if cancel_inbound:
                    cancel_dirs.add("inbound")
                if cancel_outbound:
                    cancel_dirs.add("outbound")

                applied_map = self._get_applied_qos_policies_multi(switch, ports)
                commands = []
                for port in ports:
                    for policy_name, direction in applied_map.get(port, []):
                        if direction in cancel_dirs:
                            commands.append(adapter.get_enter_interface_command(port))
                            commands.append(
                                adapter.get_undo_apply_qos_policy_command(direction, policy_name)
                            )
                            commands.append(adapter.get_exit_interface_command())

                if not commands:
                    logger.info(
                        "批量取消限速：所选 %d 个端口均未应用QoS策略，幂等跳过下发",
                        len(ports),
                    )
                    for port in ports:
                        details.append({"port": port, "success": True})
                    return {
                        "success": True,
                        "total": len(ports), "succeeded": len(ports),
                        "failed": 0, "details": details,
                    }

                result = self.dispatcher._send_config_no_save(
                    switch, commands,
                    err_label=f"批量{self._action_labels.get(action, action)}",
                    read_timeout=max(120, len(ports) * 3),
                )
                if not result["success"]:
                    return {
                        "success": False, "error": result.get("error", "SSH命令执行失败"),
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False,
                                     "error": result.get("error", "")} for p in ports],
                    }
                try:
                    self.dispatcher.save_config(switch)
                except Exception as e:
                    logger.warning("批量取消限速后统一保存配置失败: %s", e)
                sync_res = self.sync.bulk_sync_ports_from_device(switch.device_id, ports, op_type)
                for port in sync_res["succeeded"]:
                    details.append({"port": port, "success": True})
                for port, reason in sync_res["failed"]:
                    details.append({"port": port, "success": False, "error": reason})
                succeeded = sum(1 for d in details if d["success"])
                return {
                    "success": succeeded > 0,
                    "total": len(ports), "succeeded": succeeded,
                    "failed": len(ports) - succeeded, "details": details,
                }

            if action in ("enable_port", "disable_port"):
                return self._batch_enable_disable(switch, action, ports, op_type, adapter)

            inner_cmds = self._build_batch_inner_cmds(switch, action, params)
            if inner_cmds is None:
                return {
                    "success": False, "error": f"不支持的操作类型: {action}",
                    "total": len(ports), "succeeded": 0, "failed": len(ports),
                    "details": [{"port": p, "success": False, "error": f"不支持的操作类型"} for p in ports],
                }

            port_expr = self._build_port_expr(ports, switch.device_type)
            range_commands = [
                adapter.get_interface_range_command(port_expr),
                *inner_cmds,
                adapter.get_exit_interface_command(),
            ]

            def _build_pp():
                return self._build_per_port_commands(adapter, ports, inner_cmds)

            result, _mode = self._send_with_range_fallback(
                switch, len(ports), range_commands, _build_pp,
                err_label=f"批量{self._action_labels.get(action, action)}",
                read_timeout=max(120, len(ports) * 3),
            )

            if not result["success"]:
                return {
                    "success": False, "error": result.get("error", "SSH命令执行失败"),
                    "total": len(ports), "succeeded": 0, "failed": len(ports),
                    "details": [{"port": p, "success": False, "error": result.get("error", "")} for p in ports],
                }

            try:
                self.dispatcher.save_config(switch)
            except Exception as e:
                logger.warning("批量操作后统一保存配置失败: %s", e)

            sync_res = self.sync.bulk_sync_ports_from_device(switch.device_id, ports, op_type)
            for port in sync_res["succeeded"]:
                details.append({"port": port, "success": True})
            for port, reason in sync_res["failed"]:
                details.append({"port": port, "success": False, "error": reason})

            success_ports = [d["port"] for d in details if d["success"]]

            if action == "set_port_vlan" and success_ports:
                vlan_id = params.get("vlan_id")
                mode = params.get("mode", "access")
                try:
                    with self.sync._db_transaction(
                        switch.device_id, OpType.PORT_VLAN_CONFIG,
                        affected_ports=success_ports,
                    ):
                        for port in success_ports:
                            sp = self.switch_repo.session.begin_nested()
                            try:
                                self.vlan_service._update_vlan_member_relation(
                                    switch.device_id, port, vlan_id, mode,
                                    room_id=switch.device.cabinet.room_id if switch.device and switch.device.cabinet else None,
                                )
                            except Exception as e:
                                sp.rollback()
                                logger.warning("批量VLAN关联更新失败(端口 %s): %s", port, e)
                except Exception as e:
                    logger.error("批量VLAN关联更新事务失败: %s", e)

            elif action == "add_port_to_trunk" and success_ports:
                channel_id = params.get("channel_id")
                try:
                    with self.sync._db_transaction(
                        switch.device_id, OpType.LAG_MEMBER_SET,
                        affected_ports=success_ports,
                    ):
                        for port in success_ports:
                            sp = self.switch_repo.session.begin_nested()
                            try:
                                self.lag_service._update_lag_member_relation(
                                    switch.device_id, port, channel_id,
                                    device_type=switch.device_type,
                                )
                            except Exception as e:
                                sp.rollback()
                                logger.warning("批量LAG关联更新失败(端口 %s): %s", port, e)
                except Exception as e:
                    logger.error("批量LAG关联更新事务失败: %s", e)

            elif action == "remove_port_from_channel" and success_ports:
                try:
                    with self.sync._db_transaction(
                        switch.device_id, OpType.LAG_MEMBER_SET,
                        affected_ports=success_ports,
                    ):
                        for port in success_ports:
                            sp = self.switch_repo.session.begin_nested()
                            try:
                                self.lag_service._clear_lag_member_relation(switch.device_id, port)
                            except Exception as e:
                                sp.rollback()
                                logger.warning("批量LAG关联清除失败(端口 %s): %s", port, e)
                except Exception as e:
                    logger.error("批量LAG关联清除事务失败: %s", e)

        succeeded = sum(1 for d in details if d["success"])
        return {
            "success": succeeded > 0,
            "total": len(ports),
            "succeeded": succeeded,
            "failed": len(ports) - succeeded,
            "details": details,
        }

    def batch_port_action_db(self, device_id: int, action: str,
                             ports: list[str], params: dict = None) -> dict:
        """批量端口操作（非网管交换机，直接操作数据库）

        支持的操作：
        - enable_port:  批量更新 link_status='up'
        - disable_port: 批量更新 link_status='admin_down'
        - set_port_vlan: 批量更新 vlan
        - update_port_info: 批量更新 description
        - assign_customer: 批量更新 customer_id
        - add_port_to_trunk: 批量更新 lag_group_id
        - remove_port_from_channel: 批量清除 lag_group_id
        - clear_port_config: 批量恢复默认（清除vlan/description/lag，恢复为空闲启用）

        Args:
            device_id: 交换机 device_id
            action: 操作类型
            ports: 端口名称列表
            params: 操作参数

        Returns:
            dict: {total, succeeded, failed, details}
        """
        params = params or {}
        op_type = self._BATCH_OP_TYPE_MAP.get(action, OpType.PORT_UPDATE)
        details = []

        try:
            with self.sync._db_transaction(device_id, op_type,
                                              affected_ports=ports):
                for port in ports:
                    port_row = self.switch_repo.find_port_by_device_and_name(device_id, port)
                    if not port_row:
                        details.append({"port": port, "success": False, "error": "端口不存在"})
                        continue

                    savepoint = self.switch_repo.session.begin_nested()
                    try:
                        if action == "enable_port":
                            port_row.link_status = "up"
                            port_row.usage_status = "free"
                        elif action == "disable_port":
                            port_row.link_status = "admin_down"
                            port_row.usage_status = "disabled"
                        elif action == "set_port_vlan":
                            vlan_id = params.get("vlan_id")
                            port_row.vlan = str(vlan_id) if vlan_id else None
                        elif action == "update_port_info":
                            description = params.get("description", "")
                            port_row.description = description
                        elif action == "assign_customer":
                            customer_id = params.get("customer_id")
                            port_row.customer_id = customer_id
                        elif action == "add_port_to_trunk":
                            channel_id = params.get("channel_id")
                            sc = self.switch_repo.find_by_device_id(device_id)
                            dt = sc.device_type if sc else None
                            self.lag_service._update_lag_member_relation(device_id, port, channel_id, device_type=dt)
                        elif action == "remove_port_from_channel":
                            self.lag_service._clear_lag_member_relation(device_id, port)
                        elif action == "clear_port_config":
                            port_row.vlan = None
                            port_row.description = None
                            port_row.link_status = "up"
                            port_row.usage_status = "free"
                            self.lag_service._clear_lag_member_relation(device_id, port)
                        else:
                            savepoint.rollback()
                            details.append({"port": port, "success": False, "error": f"不支持的操作类型: {action}"})
                            continue

                        details.append({"port": port, "success": True})
                    except Exception as e:
                        savepoint.rollback()
                        logger.warning("非网管交换机批量操作端口 %s 失败: %s", port, e)
                        details.append({"port": port, "success": False, "error": str(e)})

        except Exception as e:
            logger.error("非网管交换机批量操作事务失败: %s", e)
            return {
                "success": False, "error": str(e),
                "total": len(ports), "succeeded": 0, "failed": len(ports),
                "details": [{"port": p, "success": False, "error": str(e)} for p in ports],
            }

        succeeded = sum(1 for d in details if d["success"])
        return {
            "success": succeeded > 0,
            "total": len(ports),
            "succeeded": succeeded,
            "failed": len(ports) - succeeded,
            "details": details,
        }

    def _batch_enable_disable(self, switch, action: str, ports: list[str],
                              op_type: str, adapter) -> dict:
        """批量启用/禁用端口：单 SSH 连接完成 config + save + 状态查询

        优化：将 undo shutdown / shutdown 下发、保存配置、读取实际链路状态
        合并到同一个 SSH 连接，避免硬编码 link_status。

        流程：
        1. 构造 interface range + undo/shutdown 命令（含 CE commit）
        2. 同一连接下发配置命令
        3. 同一连接保存配置
        4. 同一连接执行 display interface，解析实际链路状态
        5. 按实际状态更新 DB（update_port_status → derive_usage_status）
        6. 批量同步端口配置缓存 + 广播 SSE

        Args:
            switch: 交换机对象
            action: "enable_port" 或 "disable_port"
            ports: 端口名称列表
            op_type: OpType.PORT_ENABLE / OpType.PORT_DISABLE
            adapter: 设备适配器

        Returns:
            dict: {success, total, succeeded, failed, details}
        """
        inner_cmd = adapter.get_undo_shutdown_command() if action == "enable_port" else adapter.get_shutdown_command()
        port_expr = self._build_port_expr(ports, switch.device_type)
        range_commands = [
            adapter.get_interface_range_command(port_expr),
            inner_cmd,
            adapter.get_exit_interface_command(),
        ]
        device_model = getattr(switch.device, "device_model", "") or ""
        range_commands = self.dispatcher._maybe_append_commit(range_commands, adapter, device_model)

        details = []
        succeeded_ports = []

        try:
            with self.sync.ssh_mgr.get_connection(switch) as conn:
                def _build_per_port_cmds():
                    cmds = self._build_per_port_commands(adapter, ports, [inner_cmd])
                    return self.dispatcher._maybe_append_commit(cmds, adapter, device_model)

                def _send_on_conn(cmds):
                    self.sync.ssh_mgr.execute_config_on_conn(conn, cmds)

                success, _mode, error = self._execute_config_with_range_fallback(
                    _send_on_conn, _send_on_conn,
                    range_commands, _build_per_port_cmds,
                    err_label=f"批量{action}", port_count=len(ports),
                )
                if not success:
                    logger.error("批量%s 配置下发失败: %s", action, error)
                    return {
                        "success": False, "error": error,
                        "total": len(ports), "succeeded": 0, "failed": len(ports),
                        "details": [{"port": p, "success": False, "error": error} for p in ports],
                    }

                save_cmd = adapter.get_save_command(device_model)
                try:
                    self.sync.ssh_mgr.execute_show_on_conn(conn, save_cmd, timeout=60)
                except Exception as e:
                    logger.warning("批量%s 保存配置失败（不影响操作结果）: %s", action, e)

                for port in ports:
                    actual_status = None
                    try:
                        raw = self.sync.ssh_mgr.execute_show_on_conn(
                            conn, adapter.get_interface_status_command(port), timeout=60,
                        )
                        if raw and raw.strip():
                            target = normalize_port(port).lower()
                            for p in adapter.parse_ports(raw):
                                if p.port and normalize_port(p.port).lower() == target:
                                    actual_status = p.status
                                    break
                    except Exception as e:
                        logger.warning("批量%s 端口 %s 状态读取失败: %s", action, port, e)

                    if actual_status is None:
                        details.append({"port": port, "success": False, "error": "未获取到端口状态"})
                        continue
                    try:
                        self.switch_repo.update_port_status(
                            switch.device_id, port, actual_status,
                        )
                        succeeded_ports.append(port)
                        details.append({"port": port, "success": True})
                    except Exception as e:
                        logger.warning("批量%s 更新端口 %s 状态失败: %s", action, port, e)
                        details.append({"port": port, "success": False, "error": str(e)})

        except Exception as e:
            logger.error("批量%s SSH 连接失败: %s", action, e)
            return {
                "success": False, "error": f"SSH 连接失败: {e}",
                "total": len(ports), "succeeded": 0, "failed": len(ports),
                "details": [{"port": p, "success": False, "error": f"SSH 连接失败: {e}"} for p in ports],
            }

        if succeeded_ports:
            try:
                self.sync.bulk_sync_ports_from_device(
                    switch.device_id, succeeded_ports, op_type,
                )
            except Exception as e:
                logger.warning("批量%s 配置缓存同步失败（状态已更新）: %s", action, e)

        succeeded = len(succeeded_ports)
        return {
            "success": succeeded > 0,
            "total": len(ports),
            "succeeded": succeeded,
            "failed": len(ports) - succeeded,
            "details": details,
        }

    def _build_batch_inner_cmds(self, switch, action: str,
                                params: dict) -> Optional[list[str]]:
        """构造 interface range 视图内的配置命令

        该方法不处理 add_port_to_trunk（由 batch_port_action 独立路径处理，
        因 trunkport 聚合语法需要特殊处理）。

        Args:
            switch: 交换机对象
            action: 操作类型
            params: 操作参数

        Returns:
            list[str]: 接口视图内的命令列表，不支持的操作返回 None
        """
        adapter = get_adapter(switch.device_type)

        if action == "enable_port":
            return [adapter.get_undo_shutdown_command()]
        elif action == "disable_port":
            return [adapter.get_shutdown_command()]
        elif action == "set_port_vlan":
            vlan_id = params.get("vlan_id")
            mode = params.get("mode", "access")
            allowed_vlans = params.get("allowed_vlans")
            return self._build_batch_vlan_cmds(switch, vlan_id, mode, allowed_vlans)
        elif action == "update_port_info":
            description = params.get("description", "")
            if description:
                return [adapter.get_description_command(description)]
            else:
                return [adapter.get_undo_description_command()]
        elif action == "remove_port_from_channel":
            return [adapter.get_remove_member_command()]

        return None

    def _build_batch_vlan_cmds(self, switch, vlan_id: int, mode: str,
                               allowed_vlans: str = None) -> list[str]:
        """构造批量 VLAN 配置命令（interface range 视图内）

        Args:
            switch: 交换机对象
            vlan_id: VLAN ID
            mode: "access" 或 "trunk"
            allowed_vlans: Trunk 允许的 VLAN 列表

        Returns:
            list[str]: 接口视图内的 VLAN 配置命令
        """
        adapter = get_adapter(switch.device_type)
        device_model = switch.device.device_model or ""

        if mode == "access":
            return [adapter.get_set_access_vlan_command(vlan_id)]
        else:
            vlans_str = allowed_vlans if allowed_vlans else str(vlan_id)
            cmds = [
                adapter.get_set_trunk_command(),
                adapter.get_trunk_allow_command(vlans_str, device_model),
            ]
            if vlan_id != 1:
                cmds.append(adapter.get_trunk_pvid_command(vlan_id))
            return cmds

    @staticmethod
    def _coerce_speed(val) -> Optional[int]:
        """将入参限速值规整为大于 0 的 int，非法/缺失/非正数返回 None

        兼容 JSON 传入的字符串（"1000"）或浮点（1000.0），并排除布尔值。
        """
        if val is None or isinstance(val, bool):
            return None
        try:
            iv = int(val)
        except (TypeError, ValueError):
            return None
        return iv if iv > 0 else None

    def _qos_policy_exists_on_device(self, switch, adapter, policy_name: str) -> bool:
        """查询设备上是否已存在指定 QoS 策略（批量限速去重）

        复用底层 ssh_mgr 的 show 命令，逻辑与 SwitchConfigService 保持一致：
        已存在则跳过创建、直接引用。查询失败（超时/异常/无回显）时保守返回 False
        触发创建——重定义相同内容的策略在华为/H3C 上是幂等的，不会破坏其它引用端口。
        """
        try:
            output = self.dispatcher.ssh_mgr.send_show_command(
                switch, adapter.get_qos_policy_query_command(policy_name),
            )
        except Exception as e:
            logger.warning("批量限速查询QoS策略 %s 是否存在失败: %s", policy_name, e)
            return False
        if not output:
            return False
        return not adapter.is_qos_policy_missing(output)

    def _get_applied_qos_policies_multi(self, switch, ports: list, timeout: int = 120) -> dict:
        """单连接复用读取多个端口已应用的 QoS 策略（批量取消限速用）

        仅建 1 个 SSH 连接，循环 execute_show_on_conn 读取各端口配置并解析，
        替代逐端口 _get_applied_qos_policies（后者每次 send_show_command 都新建连接，
        N 端口 = N 次 SSH 握手）。返回 {port: [(policy_name, direction), ...]}。

        单端口读取失败（超时/异常/无回显）保守返回该端口 [] 并跳过撤销，
        不影响其它端口；建立连接失败则所有端口返回 []（由上层走幂等成功分支）。
        与 SwitchConfigService._get_applied_qos_policies 解析逻辑保持一致。
        """
        adapter = get_adapter(switch.device_type)
        result: dict = {}
        try:
            with self.dispatcher.ssh_mgr.get_connection(switch) as conn:
                for port in ports:
                    try:
                        config_output = self.dispatcher.ssh_mgr.execute_show_on_conn(
                            conn, f"display current-configuration interface {port}", timeout)
                        if not config_output:
                            result[port] = []
                            continue
                        result[port] = adapter.parse_qos_policies(config_output)
                    except Exception as e:
                        logger.warning("批量取消限速：读取端口 %s 已应用QoS策略失败: %s", port, e)
                        result[port] = []
        except Exception as e:
            logger.error("批量取消限速建立 SSH 连接失败: %s", e)
            for port in ports:
                result.setdefault(port, [])
        return result

    @staticmethod
    def _is_range_structural_error(error: str) -> bool:
        """判断 interface range 下发失败时是否应降级为逐端口模式重试

        逐端口模式与单端口操作路径完全一致（单端口已验证可用），且按端口细粒度下发，
        能规避 interface range 的跨板 / 类型混杂 / 端口不存在 / 超数量 / 读超时确认提示
        等问题。因此默认「range 失败即降级」——这正解决「单端口成功、多端口失败」的
        典型场景（多端口在 range 视图下常因确认提示导致 netmiko 读超时，而逐端口不会）。

        仅排除少数与 range 无关、逐端口同样必败的连接 / 鉴权故障，避免无谓的二次 SSH 尝试。
        """
        if not error:
            return False
        low = error.lower()
        no_fallback_hints = (
            "authentication failed",      # 认证失败
            "connection refused",         # 连接被拒
            "name or service not known",  # DNS 解析失败
            "no route to host",           # 路由不可达
            "tcp connection to device failed",  # 套接字级连接失败
        )
        if any(h in low for h in no_fallback_hints):
            return False
        return True

    def _execute_config_with_range_fallback(
        self, send_range_fn, send_per_port_fn,
        range_commands: list, per_port_cmds_builder,
        err_label: str, port_count: int,
    ) -> tuple[bool, str, Optional[str]]:
        """公用 range 降级执行器：优先 interface range，失败降级逐端口

        抽取自 _send_with_range_fallback（独立连接）与 _batch_enable_disable（连接复用），
        统一降级判断与日志，支持任意发送函数。

        Args:
            send_range_fn: range 模式发送函数 (commands: list[str]) -> str，失败抛异常
            send_per_port_fn: 逐端口模式发送函数 (commands: list[str]) -> str，失败抛异常
            range_commands: interface range 视图命令序列
            per_port_cmds_builder: 无参可调用，仅当降级逐端口时才调用，返回逐端口命令序列
                                   （惰性构造：range 成功时零开销）
            err_label: 操作标签（日志用）
            port_count: 端口数（日志用）

        Returns:
            tuple: (success, mode, error)
            - success: 是否成功
            - mode: "range" 或 "per_port"
            - error: 失败时的错误信息，成功时为 None
        """
        try:
            send_range_fn(range_commands)
            return True, "range", None
        except Exception as e:
            if not self._is_range_structural_error(str(e)):
                return False, "range", str(e)
            logger.warning(
                "批量操作[%s] interface range 下发失败，降级为逐端口模式重试（端口数=%d）。原因: %s",
                err_label, port_count, e,
            )
            try:
                send_per_port_fn(per_port_cmds_builder())
                logger.info("批量操作[%s] 逐端口模式重试成功", err_label)
                return True, "per_port", None
            except Exception as e2:
                logger.warning("批量操作[%s] 逐端口模式重试仍失败: %s", err_label, e2)
                return False, "per_port", str(e2)

    def _send_with_range_fallback(self, switch, port_count: int, range_commands: list,
                                  build_per_port_cmds, err_label: str, read_timeout: int):
        """优先用 interface range 一次下发；若设备拒绝 range（结构性失败），
        自动切换为逐端口模式（每条端口 interface <port> 块）重试，切换时打印日志。

        委托 _execute_config_with_range_fallback 公用降级逻辑，
        适配 _send_config_no_save 的 result_dict 返回结构与超时差异。

        Args:
            switch: 交换机对象
            port_count: 端口数（仅用于日志）
            range_commands: interface range 视图命令序列
            build_per_port_cmds: 无参可调用，返回逐端口命令序列
            err_label: 操作标签（用于日志）
            read_timeout: 超时（秒）

        Returns:
            tuple: (result_dict, mode)  mode ∈ {"range", "per_port"}
        """
        def _send_range(cmds):
            r = self.dispatcher._send_config_no_save(
                switch, cmds, err_label=err_label, read_timeout=read_timeout,
            )
            if not r["success"]:
                raise Exception(r.get("error", "SSH命令执行失败"))

        def _send_per_port(cmds):
            r = self.dispatcher._send_config_no_save(
                switch, cmds, err_label=f"{err_label}(逐端口)",
                read_timeout=min(read_timeout, 60),
            )
            if not r["success"]:
                raise Exception(r.get("error", "SSH命令执行失败"))

        success, mode, error = self._execute_config_with_range_fallback(
            _send_range, _send_per_port,
            range_commands, build_per_port_cmds, err_label, port_count,
        )
        return {"success": success, "error": error}, mode

    @staticmethod
    def _build_per_port_commands(adapter, ports: list[str], inner_cmds: list,
                                 prefix_cmds: list = None) -> list:
        """将 inner_cmds 包裹为逐端口 interface <port> ... quit 块（单次 config set 内）

        Args:
            adapter: 设备适配器
            ports: 端口列表
            inner_cmds: 接口视图内命令（每条端口相同）
            prefix_cmds: 全局视图前置命令（如共享 QoS 策略定义），仅发送一次

        Returns:
            list: 逐端口命令序列
        """
        commands = list(prefix_cmds or [])
        for port in ports:
            commands.append(adapter.get_enter_interface_command(port))
            commands.extend(inner_cmds)
            commands.append(adapter.get_exit_interface_command())
        return commands

    @staticmethod
    def _build_port_expr(ports: list[str], device_type: str) -> str:
        """将端口列表构造为 interface range 表达式

        Args:
            ports: 端口名称列表
            device_type: 设备类型

        Returns:
            str: 厂商格式的端口表达式
        """
        from app.utils.port_range_parser import PortRangeParser
        return PortRangeParser.build_range_expr(ports, device_type)
