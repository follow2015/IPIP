# -*- coding: utf-8 -*-
"""
命令分发协调器

从 SwitchConfigService 中提取的命令发送相关方法，
子服务注入此对象替代 parent 反向引用，消除循环依赖。

职责：
- _send_config / _send_config_no_save：SSH 配置命令下发
- _port_cmds：构造进入端口视图的命令序列
- _entity_exists：检查 VLAN/Trunk 是否存在
- _maybe_append_commit：华为 CE commit 追加
- save_config：保存交换机配置
"""
from app.utils.logging import get_logger
import re
from typing import Optional

from app.adapters.adapter_factory import get_adapter
from app.exceptions.system import SSHConnectionError, SwitchConfigError

logger = get_logger(__name__)


class CommandDispatcher:
    """命令分发协调器：封装 SSH 命令下发与构造逻辑"""

    def __init__(self, ssh_mgr, device_op_lock):
        """
        Args:
            ssh_mgr: SSHManager 实例
            device_op_lock: DeviceOpLock 实例（设备级操作锁）
        """
        self.ssh_mgr = ssh_mgr
        self.device_op_lock = device_op_lock

    @staticmethod
    def _classify_error(e: Exception) -> str:
        """将底层异常分类为面向用户的错误文案

        - 连接 / 认证 / 读超时（SSHConnectionError）→ SSH连接失败
        - 设备明确拒绝配置（SwitchConfigError）      → 端口配置失败（保留设备回显错误）
        - 其它                                       → 操作失败
        """
        if isinstance(e, SwitchConfigError):
            reason = (getattr(e, "details", None) or {}).get("reason") or str(e)
            return f"端口配置失败：{reason}"
        if isinstance(e, SSHConnectionError):
            msg = str(e)
            return f"SSH连接失败：{msg}" if msg and msg != "SSH 连接失败" else "SSH连接失败"
        return f"操作失败：{e}"


    @staticmethod
    def _check_id_in_output(output: str, target_id: int) -> bool:
        """在设备 display 输出中正则匹配具体 ID 编号，判断 VLAN/Trunk 是否存在

        匹配规则（按优先级）：
        1. VLAN ID 显式声明：VLAN ID: 66 / VLAN ID : 66 / VLAN ID/Name: 66
        2. 链路聚合接口名：Eth-Trunk10 / Bridge-Aggregation10 / Port-channel10 / Po10
        3. 纯数字独立出现（VLAN 场景）：行首或空白后紧跟目标数字

        Args:
            output: 设备命令原始输出
            target_id: 目标 ID（VLAN ID 或 Trunk ID）

        Returns:
            bool: 输出中匹配到具体 ID 则返回 True
        """
        if not output or not output.strip():
            return False
        text = output.strip()
        id_str = str(target_id)

        if re.search(rf"vlan\s+id\s*/?\s*name?\s*:\s*{id_str}\b", text, re.IGNORECASE):
            return True

        if re.search(
            rf"(?:eth-trunk|bridge-aggregation|port-channel|po)\s*{id_str}\b",
            text, re.IGNORECASE,
        ):
            return True

        if re.search(rf"(?:^|\s){id_str}(?:\s|$)", text, re.MULTILINE):
            return True

        return False


    def _maybe_append_commit(self, commands: list, adapter, device_model: str) -> list:
        """华为 CE 系列需要在配置命令后追加 commit

        Args:
            commands:    待发送命令列表
            adapter:     设备适配器
            device_model: 设备型号字符串

        Returns:
            list: 追加 commit 后的命令列表（非 CE 型号原样返回）
        """
        commit_cmd = adapter.get_commit_command()
        if commit_cmd and adapter.is_ce_model(device_model):
            return [*commands, commit_cmd]
        return commands

    def _port_cmds(self, switch, port: str, *inner_cmds) -> list:
        """将命令包裹在 interface → <cmds> → quit 中

        Args:
            switch: 交换机对象
            port: 端口名称
            *inner_cmds: 接口视图下执行的命令
        """
        a = get_adapter(switch.device_type)
        return [
            a.get_enter_interface_command(port),
            *inner_cmds,
            a.get_exit_interface_command(),
        ]


    def _send_config(self, switch, commands: list, *,
                     ok_extra: dict = None,
                     err_label: str = "操作") -> dict:
        """发送配置命令：自动保存，CE 自动追加 commit

        Args:
            switch:    交换机对象
            commands:  待发送命令列表
            ok_extra:  成功时附加到结果的额外字段
            err_label: 失败日志中的操作标签

        Returns:
            dict: {success: bool, ...ok_extra}
        """
        adapter = get_adapter(switch.device_type)
        commands = self._maybe_append_commit(
            commands, adapter, getattr(switch.device, "device_model", "") or "")
        try:
            self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=commands,
                save_cmd=adapter.get_save_command(getattr(switch.device, "device_model", "") or ""),
            )
            return {"success": True, **(ok_extra or {})}
        except Exception as e:
            logger.error("%s失败: %s", err_label, e)
            return {"success": False, "error": self._classify_error(e)}

    def _send_config_no_save(self, switch, commands: list, *,
                             ok_extra: dict = None,
                             err_label: str = "操作",
                             read_timeout: int = 120) -> dict:
        """发送配置命令：不保存（save 由调用方单独执行），用于批量操作中间步骤

        **CE 系列必须追加 commit**：华为 CloudEngine 的配置是 candidate 模式，
        send_config_set 退出 system-view 时会因"未提交配置"弹出
        `Uncommitted configurations found. Are you sure to commit them before exiting?`
        的交互确认，netmiko 不处理该 Y/N/C 提示 → 读超时 / 配置被丢弃。
        因此与 _send_config 保持一致：CE 在命令末尾追加 commit（仅提交到 running，
        不写 startup；写 startup 由调用方的 save_config 负责）。

        Args:
            switch:    交换机对象
            commands:  待发送命令列表
            ok_extra:  成功时附加到结果的额外字段
            err_label: 失败日志中的操作标签

        Returns:
            dict: {success: bool, ...ok_extra}
        """
        try:
            adapter = get_adapter(switch.device_type)
            commands = self._maybe_append_commit(
                commands, adapter, getattr(switch.device, "device_model", "") or "")
            self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=commands,
                save_cmd="",
                read_timeout=read_timeout,
            )
            return {"success": True, **(ok_extra or {})}
        except Exception as e:
            logger.error("%s失败: %s", err_label, e)
            return {"success": False, "error": self._classify_error(e)}

    def _entity_exists(self, switch, check_cmd: str, entity_id: int,
                       entity_name: str = "VLAN/Trunk") -> Optional[bool]:
        """通用的 VLAN/Trunk 存在性检查

        Args:
            switch:      交换机对象
            check_cmd:   检查命令（如 display vlan 66）
            entity_id:   目标 ID
            entity_name: 实体名称（仅用于日志）

        Returns:
            Optional[bool]:
                True  — 设备上存在
                False — 设备上不存在
                None  — SSH 检查失败（无法判定），调用方不应触发补创
        """
        try:
            with self.ssh_mgr.get_connection(switch) as conn:
                output = self.ssh_mgr.execute_command(conn, check_cmd)
            return self._check_id_in_output(output, entity_id)
        except Exception as e:
            logger.warning("检查 %s %d 存在性失败: %s", entity_name, entity_id, e)
            return None

    def save_config(self, switch) -> dict:
        """保存交换机配置（复用重试机制）"""
        adapter = get_adapter(switch.device_type)
        try:
            self.ssh_mgr.send_config_commands(switch, [], save_cmd=adapter.get_save_command(switch.device.device_model or ""))
            return {"success": True, "message": "配置已保存"}
        except Exception as e:
            logger.error("保存配置失败: %s", e)
            return {"success": False, "error": str(e)}
