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
    """端口清除子服务"""

    def __init__(self, dispatcher, switch_repo: SwitchRepository, sync_coordinator, ssh_mgr=None):
        """
        Args:
            dispatcher: CommandDispatcher 实例，用于命令下发
            switch_repo: SwitchRepository 实例
            sync_coordinator: SyncCoordinator 实例，用于 _get_port_members 等共享能力
            ssh_mgr: SSHManager 实例（用于交互式命令）
        """
        self.dispatcher = dispatcher
        self.switch_repo = switch_repo
        self.sync = sync_coordinator
        self.ssh_mgr = ssh_mgr


    def _clear_port_config_on_device(self, switch, port: str,
                                     auto_save: bool = True) -> dict:
        """在设备上清除端口配置（仅 SSH 操作，不更新数据库）

        物理端口：在系统视图下执行 clear configuration interface <port>，
        自动输入 Y 确认，清除后进入接口视图执行 undo shutdown 恢复端口开启。
        若物理端口属于 Eth-Trunk 成员，先执行 undo eth-trunk 从 Trunk 中剥离。

        Eth-Trunk 接口：进入接口视图后执行 clear configuration this，
        无需先解绑成员（this 模式下设备自动处理成员关系），
        清除后执行 undo shutdown 恢复端口开启。

        Args:
            switch: 交换机对象
            port: 端口名称
            auto_save: 是否在命令执行后自动保存配置（批量操作时关闭，最后统一保存）

        Returns:
            dict: {success: bool, error?: str}
        """
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
        """从配置缓存中解析端口所属的 Eth-Trunk ID

        Args:
            device_id: 交换机 device_id
            port: 端口名称

        Returns:
            Eth-Trunk ID（如 10），不属于任何 Trunk 时返回 None
        """
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
        """批量清除端口配置（合并 SSH 交互步骤，一次连接完成所有端口）

        将所有端口的 clear configuration 步骤合并为一条交互式命令序列，
        一次 SSH 连接执行完毕，避免逐端口建立连接的开销。

        Eth-Trunk 端口使用 clear configuration this（接口视图内），
        物理端口使用 clear configuration interface <port>（系统视图下），
        两者交互步骤不同，Eth-Trunk 端口单独逐个处理。

        Args:
            switch: 交换机对象
            ports: 端口名称列表
            auto_save: 是否在执行后自动保存（批量操作时关闭，由调用方统一保存）
        """
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

