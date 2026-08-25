# -*- coding: utf-8 -*-
"""
链路聚合子服务

从 SwitchConfigService 拆分出的 LAG（链路聚合）相关操作：
- add_port_to_channel / delete_eth_trunk / create_port_channel / remove_port_from_channel
- _ensure_trunk_exists / _clear_lag_member_relation / _update_lag_member_relation
- _get_trunk_name（静态辅助）

依赖注入：通过 CommandDispatcher 和 SyncCoordinator 访问共享能力，
不再持有 parent（Facade）反向引用，消除循环依赖。
"""
from app.utils.logging import get_logger

from app.adapters.adapter_factory import get_adapter
from app.persistence.switch_repo import SwitchRepository
from app.services.switch_event_schema import OpType
from app.services.device_op_lock import device_op_lock
from app.utils.port_name_utils import is_trunk_interface, extract_trunk_id, get_trunk_name

logger = get_logger(__name__)


class LagConfigService:

    def __init__(self, dispatcher, switch_repo: SwitchRepository, sync_coordinator,
                 clear_service=None):
        self.dispatcher = dispatcher
        self.switch_repo = switch_repo
        self.sync = sync_coordinator
        self.clear_service = clear_service


    @staticmethod
    def _is_trunk_interface(port: str) -> bool:
        return is_trunk_interface(port)

    @staticmethod
    def _extract_trunk_id(port: str):
        return extract_trunk_id(port)

    @staticmethod
    def _get_trunk_name(device_type: str, channel_id: int) -> str:
        return get_trunk_name(device_type, channel_id)


    def create_port_channel(self, switch, channel_id: int, member_ports: list) -> dict:
        adapter = get_adapter(switch.device_type)
        commands = [adapter.get_create_trunk_command(channel_id)]
        result = self.dispatcher._send_config(switch, commands, err_label="创建Eth-Trunk")
        if not result["success"]:
            return {**result, "channel_id": channel_id}

        trunk_name = self._get_trunk_name(switch.device_type, channel_id)
        lag_row = self.switch_repo.find_lag_by_device_and_name(switch.device_id, trunk_name)
        with self.sync._db_transaction(switch.device_id, OpType.LAG_CREATE,
                                        affected_ports=[trunk_name],
                                        affected_lags=[lag_row.id] if lag_row else []):
            self.switch_repo.update_vlan_trunk_info(switch.device_id, trunk_name)

        for port in member_ports:
            member_result = self.dispatcher._send_config(
                switch,
                self.dispatcher._port_cmds(switch, port, adapter.get_add_member_command(channel_id)),
                err_label=f"添加成员端口到Eth-Trunk {channel_id}",
            )
            if member_result["success"]:
                self.sync._sync_port_from_device(switch.device_id, port, OpType.LAG_MEMBER_SET)
        return {"success": True, "message": f"Eth-Trunk {channel_id} 已创建"}

    def delete_eth_trunk(self, switch, trunk_id: int) -> dict:
        if not (1 <= trunk_id <= 512):
            return {"success": False, "error": f"Trunk ID {trunk_id} 超出合法范围 1-512"}

        adapter = get_adapter(switch.device_type)
        trunk_name = self._get_trunk_name(switch.device_type, trunk_id)

        members = self.sync._get_port_members(switch, trunk_name, "trunk")
        if members:
            logger.info("删除 Eth-Trunk %s 前，先移除 %d 个成员", trunk_name, len(members))
            remove_cmds = []
            for member in members:
                remove_cmds.extend(self.dispatcher._port_cmds(switch, member, adapter.get_remove_member_command()))
            try:
                self.dispatcher._send_config_no_save(switch, remove_cmds, err_label="批量移除Trunk成员")
            except Exception as e:
                logger.warning("批量移除 Trunk 成员失败，降级为逐端口: %s", e)
                for member in members:
                    try:
                        self.dispatcher._send_config_no_save(
                            switch,
                            self.dispatcher._port_cmds(switch, member, adapter.get_remove_member_command()),
                            err_label="移除Trunk成员",
                        )
                    except Exception as ex:
                        logger.warning("移除 Trunk 成员 %s 失败: %s", member, ex)

            self.clear_service._batch_clear_ports(switch, members, auto_save=False)

            for member in members:
                try:
                    self.sync._sync_port_from_device(
                        switch.device_id, member, OpType.LAG_MEMBER_SET,
                        affected_ports=[member],
                    )
                    with self.sync._db_transaction(
                        switch.device_id, OpType.LAG_MEMBER_SET,
                        affected_ports=[member],
                    ):
                        self._clear_lag_member_relation(switch.device_id, member)
                except Exception as e:
                    logger.warning("移除 Trunk 成员 %s 后同步失败: %s", member, e)

        commands = [adapter.get_delete_trunk_command(trunk_id)]
        result = self.dispatcher._send_config(
            switch, commands,
            ok_extra={"message": f"Eth-Trunk {trunk_id} 已删除"},
            err_label="删除Eth-Trunk",
        )
        if result["success"]:
            lag_row = self.switch_repo.find_lag_by_device_and_name(switch.device_id, trunk_name)
            with self.sync._db_transaction(switch.device_id, OpType.LAG_DELETE,
                                            affected_ports=[trunk_name] + members,
                                            affected_lags=[lag_row.id] if lag_row else []):
                self.switch_repo.delete_vlan_trunk_info(switch.device_id, trunk_name)
                self.switch_repo.delete_port_config(switch.device_id, trunk_name)

                if lag_row:
                    self.switch_repo.delete_lag_record_by_obj(lag_row)
        return result

    def add_port_to_channel(self, switch, channel_id: int, port: str) -> dict:
        trunk_result = self._ensure_trunk_exists(switch, channel_id)
        if not trunk_result.get("success"):
            return {
                "success": False,
                "error": f"Eth-Trunk {channel_id} 自动创建失败: {trunk_result.get('error', '')}",
            }

        clear_result = self.clear_service._clear_port_config_on_device(switch, port, auto_save=False)
        if not clear_result.get("success"):
            logger.warning("加入Trunk前清除端口 %s 配置失败（继续尝试加入）: %s",
                           port, clear_result.get("error", ""))

        a = get_adapter(switch.device_type)
        result = self.dispatcher._send_config(
            switch,
            self.dispatcher._port_cmds(switch, port, a.get_add_member_command(channel_id)),
            ok_extra={"message": f"端口 {port} 已加入Eth-Trunk {channel_id}"},
            err_label="添加端口到链路聚合",
        )
        if result["success"]:
            trunk_name = self._get_trunk_name(switch.device_type, channel_id)
            lag_row = self.switch_repo.find_lag_by_device_and_name(switch.device_id, trunk_name)
            self.sync._sync_port_from_device(
                switch.device_id, port, OpType.LAG_MEMBER_SET,
                affected_lags=[lag_row.id] if lag_row else [],
            )
            self._update_lag_member_relation(switch.device_id, port, channel_id, device_type=switch.device_type)
        return result

    def remove_port_from_channel(self, switch, port: str) -> dict:
        a = get_adapter(switch.device_type)
        port_row = self.switch_repo.find_port_by_device_and_name(switch.device_id, port)
        lag_id = port_row.lag_group_id if port_row and port_row.lag_group_id else None

        with device_op_lock.acquire(switch.device_id):
            result = self.dispatcher._send_config(
                switch,
                self.dispatcher._port_cmds(switch, port, a.get_remove_member_command()),
                ok_extra={"message": f"端口 {port} 已从链路聚合组移除"},
                err_label="从链路聚合组移除端口",
            )
            if result["success"]:
                self.sync._sync_port_from_device(
                    switch.device_id, port, OpType.LAG_MEMBER_SET,
                    affected_lags=[lag_id] if lag_id else [],
                )

        if result["success"]:
            self._clear_lag_member_relation(switch.device_id, port)
        return result

    def _ensure_trunk_exists(self, switch, channel_id: int) -> dict:
        adapter = get_adapter(switch.device_type)
        check_cmd = adapter.get_check_trunk_command(channel_id)

        entity_check = self.dispatcher._entity_exists(switch, check_cmd, channel_id, "Eth-Trunk")
        if entity_check is True:
            return {"success": True, "message": f"Eth-Trunk {channel_id} 已存在"}
        if entity_check is None:
            logger.warning("Eth-Trunk %d 存在性检查失败（SSH异常），尝试创建", channel_id)

        trunk_name = self._get_trunk_name(switch.device_type, channel_id)
        commands = [adapter.get_create_trunk_command(channel_id)]
        result = self.dispatcher._send_config(
            switch, commands,
            ok_extra={"message": f"Eth-Trunk {channel_id} 已自动创建"},
            err_label="自动创建Eth-Trunk",
        )
        if result["success"]:
            with self.sync._db_transaction(switch.device_id, OpType.LAG_UPDATE,
                                            affected_ports=[trunk_name]):
                self.switch_repo.update_vlan_trunk_info(switch.device_id, trunk_name)
        return result

    def _update_lag_member_relation(self, device_id: int, port_name: str,
                                     channel_id: int, device_type: str = None) -> None:
        if not (1 <= channel_id <= 512):
            logger.warning("_update_lag_member_relation: Trunk ID %d 超出合法范围 1-512，跳过", channel_id)
            return

        self.switch_repo.update_lag_member_relation(device_id, port_name, channel_id, device_type=device_type)

    def _clear_lag_member_relation(self, device_id: int, port_name: str) -> None:
        self.switch_repo.clear_lag_member_relation(device_id, port_name)
