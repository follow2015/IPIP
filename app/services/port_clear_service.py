# -*- coding: utf-8 -*-
"""
端口清除子服务

从 SwitchConfigService 拆分出的端口配置清除相关操作：
- _clear_port_config_on_device / _batch_clear_ports
"""
from app.utils.logging import get_logger

from app.adapters.adapter_factory import get_adapter
from app.persistence.switch_repo import SwitchRepository
from app.utils.port_name_utils import is_trunk_interface

logger = get_logger(__name__)


class PortClearService:

    def __init__(self, dispatcher, switch_repo: SwitchRepository, sync_coordinator, ssh_mgr=None):
        self.dispatcher = dispatcher
        self.switch_repo = switch_repo
        self.sync = sync_coordinator
        self.ssh_mgr = ssh_mgr


    def _clear_port_config_on_device(self, switch, port: str,
                                     auto_save: bool = True) -> dict:
        if not switch:
            return {"success": False, "message": "交换机不存在"}
        adapter = get_adapter(switch.device_type)
        clear_cmd = adapter.get_clear_config_command(port)
        if not clear_cmd:
            return {"success": False, "message": "该设备类型不支持清除端口配置"}

        prompt = r"[\]\>]"

        if is_trunk_interface(port):
            steps = [
                (adapter.get_system_view_command(), prompt),
                (adapter.get_enter_interface_command(port), prompt),
                ("clear configuration this", r"\[Y/N\]"),
                ("y", prompt),
                (adapter.get_undo_shutdown_command(), prompt),
                (adapter.get_exit_interface_command(), prompt),
            ]
        else:
            trunk_id = self._get_port_trunk_id(switch.device_id, port)
            if trunk_id is not None:
                logger.info("端口 %s 属于 Eth-Trunk %d，先剥离再 clear", port, trunk_id)
                try:
                    undo_cmd = self.dispatcher._port_cmds(switch, port, "undo eth-trunk")
                    if auto_save:
                        self.dispatcher._send_config(switch, undo_cmd, err_label="剥离Trunk成员")
                    else:
                        self.dispatcher._send_config_no_save(switch, undo_cmd, err_label="剥离Trunk成员")
                except Exception as e:
                    logger.warning("剥离端口 %s 的 Trunk 成员关系失败: %s", port, e)

            steps = [
                (adapter.get_system_view_command(), prompt),
                (clear_cmd, r"\[Y/N\]"),
                ("y", prompt),
                (adapter.get_enter_interface_command(port), prompt),
                (adapter.get_undo_shutdown_command(), prompt),
                (adapter.get_exit_interface_command(), prompt),
            ]

        try:
            save_cmd = adapter.get_save_command(switch.device.device_model or "") if auto_save else ""
            self.ssh_mgr.send_interactive_command(
                switch, steps, save_cmd=save_cmd,
            )
        except Exception as e:
            logger.error("清除端口配置失败: %s", e)
            return {"success": False, "error": str(e)}

        return {"success": True}

    def _get_port_trunk_id(self, device_id: int, port: str):
        config_text = self.switch_repo.get_port_config_text(device_id, port)
        if not config_text:
            return None
        switch = self.switch_repo.find_by_device_id(device_id)
        if not switch:
            return None
        adapter = get_adapter(switch.device_type)
        return adapter.parse_trunk_id(config_text)

    def _batch_clear_ports(self, switch, ports: list[str],
                           auto_save: bool = True) -> None:
        if not switch or not ports:
            return

        adapter = get_adapter(switch.device_type)
        prompt = r"[\]\>]"

        trunk_ports = [p for p in ports if is_trunk_interface(p)]
        normal_ports = [p for p in ports if not is_trunk_interface(p)]

        for port in trunk_ports:
            try:
                result = self._clear_port_config_on_device(switch, port, auto_save=False)
                if not result.get("success"):
                    logger.warning("批量操作前清除 Eth-Trunk %s 配置失败: %s",
                                   port, result.get("error", ""))
            except Exception as e:
                logger.warning("批量操作前清除 Eth-Trunk %s 配置异常: %s", port, e)

        if normal_ports:
            all_steps = [(adapter.get_system_view_command(), prompt)]

            for port in normal_ports:
                all_steps.extend([
                    (adapter.get_clear_config_command(port), r"\[Y/N\]"),
                    ("y", prompt),
                    (adapter.get_enter_interface_command(port), prompt),
                    (adapter.get_undo_shutdown_command(), prompt),
                    (adapter.get_exit_interface_command(), prompt),
                ])

            try:
                logger.info("批量清除 %d 个普通端口配置，共 %d 个交互步骤",
                            len(normal_ports), len(all_steps))
                save_cmd = adapter.get_save_command(switch.device.device_model or "") if auto_save else ""
                self.ssh_mgr.send_interactive_command(
                    switch, all_steps, save_cmd=save_cmd,
                )
            except Exception as e:
                logger.error("批量清除普通端口配置失败: %s", e)
                logger.info("降级为逐端口清除模式")
                for port in normal_ports:
                    try:
                        self._clear_port_config_on_device(switch, port, auto_save=auto_save)
                    except Exception as ex:
                        logger.warning("降级清除端口 %s 失败: %s", port, ex)
