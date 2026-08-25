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

    def __init__(self, ssh_mgr, device_op_lock):
        self.ssh_mgr = ssh_mgr
        self.device_op_lock = device_op_lock

    @staticmethod
    def _classify_error(e: Exception) -> str:
        if isinstance(e, SwitchConfigError):
            reason = (getattr(e, "details", None) or {}).get("reason") or str(e)
            return f"端口配置失败：{reason}"
        if isinstance(e, SSHConnectionError):
            msg = str(e)
            return f"SSH连接失败：{msg}" if msg and msg != "SSH 连接失败" else "SSH连接失败"
        return f"操作失败：{e}"


    @staticmethod
    def _check_id_in_output(output: str, target_id: int) -> bool:
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
        commit_cmd = adapter.get_commit_command()
        if commit_cmd and adapter.is_ce_model(device_model):
            return [*commands, commit_cmd]
        return commands

    def _port_cmds(self, switch, port: str, *inner_cmds) -> list:
        a = get_adapter(switch.device_type)
        return [
            a.get_enter_interface_command(port),
            *inner_cmds,
            a.get_exit_interface_command(),
        ]


    def _send_config(self, switch, commands: list, *,
                     ok_extra: dict = None,
                     err_label: str = "操作") -> dict:
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
        try:
            with self.ssh_mgr.get_connection(switch) as conn:
                output = self.ssh_mgr.execute_command(conn, check_cmd)
            return self._check_id_in_output(output, entity_id)
        except Exception as e:
            logger.warning("检查 %s %d 存在性失败: %s", entity_name, entity_id, e)
            return None

    def save_config(self, switch) -> dict:
        adapter = get_adapter(switch.device_type)
        try:
            self.ssh_mgr.send_config_commands(switch, [], save_cmd=adapter.get_save_command(switch.device.device_model or ""))
            return {"success": True, "message": "配置已保存"}
        except Exception as e:
            logger.error("保存配置失败: %s", e)
            return {"success": False, "error": str(e)}
