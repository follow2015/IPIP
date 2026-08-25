# -*- coding: utf-8 -*-
"""
VLAN 配置子服务

从 SwitchConfigService 拆分出的 VLAN 相关操作：
- create_vlan / delete_vlan / set_port_vlan
- _ensure_vlan_record / _update_vlan_member_relation / _sync_vlan_members
- _get_vlanif_name（静态辅助）
"""
from app.utils.logging import get_logger

from app.adapters.adapter_factory import get_adapter
from app.persistence.switch_repo import SwitchRepository
from app.services.switch_events import emit_resource_change
from app.services.switch_event_schema import OpType
from app.utils.port_name_utils import get_vlanif_name

logger = get_logger(__name__)

class VlanConfigService:

    def __init__(self, dispatcher, switch_repo: SwitchRepository, sync_coordinator,
                 clear_service=None):
        self.dispatcher = dispatcher
        self.switch_repo = switch_repo
        self.sync = sync_coordinator
        self.clear_service = clear_service


    def create_vlan(self, switch, vlan_id: int) -> dict:
        if not (1 <= vlan_id <= 4094):
            return {"success": False, "error": f"VLAN ID {vlan_id} 超出合法范围 1-4094"}

        adapter = get_adapter(switch.device_type)
        vlanif_name = get_vlanif_name(switch.device_type, vlan_id)

        existing = self.switch_repo.find_vlan_by_device_and_id(switch.device_id, vlan_id)
        if existing:
            check_cmd = adapter.get_check_vlan_command(vlan_id)
            entity_check = self.dispatcher._entity_exists(switch, check_cmd, vlan_id, "VLAN")
            if entity_check is False:
                logger.warning("VLAN %d 库中存在但设备上不存在，补发 SSH 创建", vlan_id)
                commands = [
                    adapter.get_create_vlan_command(vlan_id),
                    adapter.get_interface_vlan_command(vlan_id),
                ]
                result = self.dispatcher._send_config(
                    switch, commands,
                    ok_extra={"message": f"VLAN {vlan_id} 已补创"},
                    err_label="补创VLAN",
                )
                if not result["success"]:
                    return result
            elif entity_check is None:
                logger.warning("VLAN %d 库网一致性检查失败（SSH异常），跳过补创", vlan_id)

            with self.sync._db_transaction(switch.device_id, OpType.VLAN_UPDATE,
                                              affected_ports=[vlanif_name],
                                              affected_vlans=[existing.id]):
                self.switch_repo.update_vlan_trunk_info(switch.device_id, vlanif_name)
            return {"success": True, "message": f"VLAN {vlan_id} 已存在，跳过创建"}

        commands = [
            adapter.get_create_vlan_command(vlan_id),
            adapter.get_interface_vlan_command(vlan_id),
        ]
        result = self.dispatcher._send_config(
            switch, commands,
            ok_extra={"message": f"VLAN {vlan_id} 已创建"},
            err_label="创建VLAN",
        )
        if result["success"]:
            with self.sync._db_transaction(switch.device_id, OpType.VLAN_CREATE,
                                              affected_ports=[vlanif_name]):
                self.switch_repo.update_vlan_trunk_info(switch.device_id, vlanif_name)
            vlan_row = self._ensure_vlan_record(switch.device_id, vlan_id, room_id=switch.device.cabinet.room_id if switch.device and switch.device.cabinet else None)
            if vlan_row:
                emit_resource_change(switch.device_id, OpType.VLAN_CREATE,
                                     affected_vlans=[vlan_row.id])
        return result

    def delete_vlan(self, switch, vlan_id: int) -> dict:
        if not (1 <= vlan_id <= 4094):
            return {"success": False, "error": f"VLAN ID {vlan_id} 超出合法范围 1-4094"}

        adapter = get_adapter(switch.device_type)
        vlanif_name = get_vlanif_name(switch.device_type, vlan_id)
        commands = [
            adapter.get_delete_interface_command(vlanif_name),
            adapter.get_delete_vlan_command(vlan_id),
        ]
        result = self.dispatcher._send_config(
            switch, commands,
            ok_extra={"message": f"VLAN {vlan_id} 已删除"},
            err_label="删除VLAN",
        )
        if result["success"]:
            vlan_db_id = None
            affected_ports = []
            try:
                vlan_row = self.switch_repo.find_vlan_by_device_and_id(switch.device_id, vlan_id)
                vlan_db_id = vlan_row.id if vlan_row else None

                affected_ports = self.switch_repo.get_ports_by_vlan(switch.device_id, vlan_id)

                if affected_ports:
                    try:
                        self.clear_service._batch_clear_ports(switch, affected_ports, auto_save=True)
                    except Exception as ssh_err:
                        logger.error("VLAN %d 删除后清除端口配置失败（SSH）: %s", vlan_id, ssh_err)
                        return {"success": False, "error": f"清除端口配置失败: {ssh_err}"}

                with self.sync._db_transaction(
                    switch.device_id, OpType.VLAN_DELETE,
                    affected_ports=[vlanif_name],
                    affected_vlans=[vlan_db_id] if vlan_db_id else [],
                ):
                    if affected_ports:
                        self.switch_repo.reset_ports_vlan(switch.device_id, vlan_id, new_vlan=1)

                    self.switch_repo.delete_vlan_trunk_info(switch.device_id, vlanif_name)
                    vlan_name = f"vlan {vlan_id}"
                    self.switch_repo.delete_vlan_trunk_info(switch.device_id, vlan_name)
                    self.switch_repo.delete_port_config(switch.device_id, vlanif_name)
                    self.switch_repo.delete_port_config(switch.device_id, vlan_name)

                    self.switch_repo.clear_connection_vlan_refs(switch.device_id, vlan_id)

                    self.switch_repo.delete_port_ips_by_vlan(switch.device_id, vlan_id)

                    if vlan_row:
                        self.switch_repo.delete_vlan_record(vlan_row)
            except Exception as e:
                logger.error("VLAN %d 删除后数据库清理失败: %s", vlan_id, e)
                affected_ports = []
                emit_resource_change(
                    device_id=switch.device_id,
                    op_type=OpType.VLAN_DELETE,
                    affected_ports=[vlanif_name],
                    affected_vlans=[vlan_db_id] if vlan_db_id else [],
                )

            if affected_ports:
                logger.info("VLAN %d 删除后，%d 个端口 VLAN 已重置为 1: %s",
                            vlan_id, len(affected_ports), ", ".join(affected_ports))
        return result

    def set_port_vlan(self, switch, port: str, vlan_id: int,
                      mode: str = "access", allowed_vlans: str = None) -> dict:
        vlan_result = self.create_vlan(switch, vlan_id)
        if not vlan_result.get("success"):
            return {
                "success": False,
                "error": f"VLAN {vlan_id} 自动创建失败: {vlan_result.get('error', '')}",
            }

        if mode == "trunk" and allowed_vlans:
            from app.adapters.base_adapter import BaseDeviceAdapter
            vlan_ranges = BaseDeviceAdapter.parse_vlan_ranges(allowed_vlans)
            for start, end in vlan_ranges:
                for vid in range(start, end + 1):
                    if vid == vlan_id:
                        continue
                    self.create_vlan(switch, vid)

        clear_result = self.clear_service._clear_port_config_on_device(switch, port, auto_save=False)
        if not clear_result.get("success"):
            logger.warning("加入VLAN前清除端口 %s 配置失败（继续尝试加入）: %s",
                           port, clear_result.get("error", ""))

        commands, _ = self._build_port_vlan_cmds(switch, port, vlan_id, mode,
                                                          allowed_vlans=allowed_vlans)
        result = self.dispatcher._send_config(switch, commands, err_label="设置端口VLAN")
        if result["success"]:
            result["message"] = f"端口 {port} VLAN已设置为 {vlan_id}"
            self.sync._sync_port_from_device(switch.device_id, port, OpType.PORT_VLAN_CONFIG)
            self._update_vlan_member_relation(switch.device_id, port, vlan_id, mode,
                                              room_id=switch.device.cabinet.room_id if switch.device and switch.device.cabinet else None)
        return result

    def _ensure_vlan_record(self, device_id: int, vlan_id: int,
                            room_id: int = None) -> None:
        if not (1 <= vlan_id <= 4094):
            logger.warning("_ensure_vlan_record: VLAN ID %d 超出合法范围 1-4094，跳过", vlan_id)
            return

        self.switch_repo.upsert_vlan_record(device_id, vlan_id, room_id=room_id)

    def _update_vlan_member_relation(self, device_id: int, port_name: str,
                                      vlan_id: int, mode: str,
                                      room_id: int = None) -> None:
        if not (1 <= vlan_id <= 4094):
            logger.warning("_update_vlan_member_relation: VLAN ID %d 超出合法范围 1-4094，跳过", vlan_id)
            return

        self.switch_repo.update_vlan_member_relation(
            device_id, port_name, vlan_id, mode, room_id=room_id,
        )

    def _sync_vlan_members(self, device_id: int, port: str, members: list) -> None:
        self.switch_repo.sync_vlan_members(device_id, port, members)

    def _build_port_vlan_cmds(
        self, switch, port: str, vlan_id: int, mode: str,
        allowed_vlans: str = None,
    ) -> tuple[list, str]:
        a = get_adapter(switch.device_type)
        current_vlan = self.switch_repo.get_port_vlan(switch.device_id, port)
        mode_cmd = a.get_portswitch_command() if current_vlan is None else ""

        if mode == "access":
            inner = [a.get_set_access_vlan_command(vlan_id)]
        else:
            vlans_str = allowed_vlans if allowed_vlans else str(vlan_id)
            device_model = switch.device.device_model or ""
            inner = [a.get_set_trunk_command(), a.get_trunk_allow_command(vlans_str, device_model)]
            if vlan_id != 1:
                inner.append(a.get_trunk_pvid_command(vlan_id))

        if mode_cmd:
            inner = [mode_cmd, *inner]

        return self.dispatcher._port_cmds(switch, port, *inner), mode_cmd
