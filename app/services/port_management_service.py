# -*- coding: utf-8 -*-
"""
统一端口管理服务

同时适配有权限/无权限交换机，提供物理端口/VLAN/LAG/连接的 CRUD 操作。
所有写操作 commit 后通过 emit_resource_change 广播结构化事件。
"""
from __future__ import annotations

from app.utils.logging import get_logger
from typing import Dict, List

from app.models.network_port import NetworkPort
from app.models.vlan import VLAN
from app.models.vlan_port_member import VLANPortMember
from app.models.link_aggregation import LinkAggregationGroup
from app.persistence.switch_port_repository import NetworkPortRepository
from app.persistence.vlan_repository import VLANRepository, VLANPortMemberRepository
from app.persistence.link_aggregation_repository import LinkAggregationRepository
from app.persistence.device_connection_repository import DeviceConnectionRepository
from app.persistence.network_connection_repository import NetworkConnectionRepository
from app.services.switch_event_schema import OpType
from app.services.switch_events import emit_resource_change
from app.utils.port_name_parser import parse_port_name
from app.exceptions.validation import ValidationError
from app.services.vlan_service import VLANService

logger = get_logger(__name__)


class PortManagementService:

    def __init__(
        self,
        port_repo: NetworkPortRepository,
        vlan_repo: VLANRepository,
        vpm_repo: VLANPortMemberRepository,
        lag_repo: LinkAggregationRepository,
        conn_repo: DeviceConnectionRepository,
        n2n_repo: NetworkConnectionRepository,
    ):
        self.port_repo = port_repo
        self.vlan_repo = vlan_repo
        self.vpm_repo = vpm_repo
        self.lag_repo = lag_repo
        self.conn_repo = conn_repo
        self.n2n_repo = n2n_repo


    def create_port(self, device_id: int, data: Dict) -> NetworkPort:
        port_name = data.get("port_name")
        if not port_name:
            raise ValidationError("端口名称不能为空")

        existing = self.port_repo.find_port_by_name(device_id, port_name)
        if existing:
            raise ValidationError(f"端口 {port_name} 已存在")

        parsed = parse_port_name(port_name)

        port = NetworkPort(
            device_id=device_id,
            port_name=port_name,
            port_type=data.get("port_type") or parsed.get("port_type"),
            slot=data.get("slot", parsed.get("slot", 0)),
            card=data.get("card", parsed.get("card", 0)),
            port_number=data.get("port_number", parsed.get("port_number", 0)),
            speed=data.get("speed", ""),
            usage_status=data.get("usage_status", "free"),
            vlan=data.get("vlan"),
            description=data.get("description", ""),
            customer_id=data.get("customer_id"),
            data_source="manual",
        )
        self.port_repo.session.add(port)

        emit_resource_change(
            device_id, OpType.PORT_CREATE,
            affected_ports=[port_name],
        )
        logger.info("手动创建端口 device=%d port=%s", device_id, port_name)
        return port

    def update_port(self, port_id: int, data: Dict) -> NetworkPort:
        port = self.port_repo.find_by_id_orm(port_id)
        if not port:
            raise ValidationError(f"端口不存在 (ID: {port_id})")

        allowed = {"usage_status", "description", "vlan", "customer_id", "port_type", "speed"}
        for field in allowed:
            if field in data:
                setattr(port, field, data[field])

        emit_resource_change(
            port.device_id, OpType.PORT_UPDATE,
            affected_ports=[port.port_name],
        )
        logger.info("更新端口 port_id=%d", port_id)
        return port

    def delete_port(self, port_id: int) -> bool:
        port = self.port_repo.find_by_id_orm(port_id)
        if not port:
            raise ValidationError(f"端口不存在 (ID: {port_id})")

        device_id = port.device_id
        port_name = port.port_name

        if port.lag_group_id:
            lag_id = port.lag_group_id
            port.lag_group_id = None
            lag = self.lag_repo.find_by_id(lag_id)
            if lag:
                lag.member_count = self.port_repo.count_ports_by_lag_group_id(lag_id) - 1

        self.vpm_repo.delete_by_port_id(port_id)

        if port.vlan:
            port.vlan = None

        self.port_repo.session.delete(port)

        emit_resource_change(
            device_id, OpType.PORT_DELETE,
            affected_ports=[port_name],
        )
        logger.info("删除端口 port_id=%d port=%s", port_id, port_name)
        return True


    def create_vlan(self, device_id: int, data: Dict) -> VLAN:
        data["device_id"] = device_id

        existing = self.vlan_repo.find_by_device_and_vlan_id(device_id, data["vlan_id"])
        if existing:
            raise ValidationError(f"设备上 VLAN {data['vlan_id']} 已存在")

        if not data.get("room_id"):
            data["room_id"] = VLANService._derive_room_id(device_id)

        vlan = self.vlan_repo.create(data)

        emit_resource_change(
            device_id, OpType.VLAN_CREATE,
            affected_vlans=[vlan.id],
        )
        logger.info("创建 VLAN device=%d vlan_id=%d", device_id, vlan.vlan_id)
        return vlan

    def update_vlan(self, vlan_db_id: int, data: Dict) -> VLAN:
        vlan = self.vlan_repo.find_by_id(vlan_db_id)
        if not vlan:
            raise ValidationError(f"VLAN 不存在 (ID: {vlan_db_id})")

        for key, value in data.items():
            if hasattr(vlan, key) and key not in ("id", "device_id", "created_at"):
                setattr(vlan, key, value)

        emit_resource_change(
            vlan.device_id, OpType.VLAN_UPDATE,
            affected_vlans=[vlan_db_id],
        )
        logger.info("更新 VLAN vlan_db_id=%d", vlan_db_id)
        return vlan

    def delete_vlan(self, vlan_db_id: int) -> bool:
        vlan = self.vlan_repo.find_by_id(vlan_db_id)
        if not vlan:
            raise ValidationError(f"VLAN 不存在 (ID: {vlan_db_id})")

        device_id = vlan.device_id

        if vlan.vlan_id:
            self.port_repo.clear_vlan_by_device_and_vlan(device_id, str(vlan.vlan_id))

        self.vpm_repo.delete_by_vlan_id(vlan_db_id)

        self.vlan_repo.session.delete(vlan)

        emit_resource_change(
            device_id, OpType.VLAN_DELETE,
            affected_vlans=[vlan_db_id],
        )
        logger.info("删除 VLAN vlan_db_id=%d", vlan_db_id)
        return True

    def update_vlan_members(self, vlan_db_id: int, port_ids: List[int]) -> None:
        vlan = self.vlan_repo.find_by_id(vlan_db_id)
        if not vlan:
            raise ValidationError(f"VLAN 不存在 (ID: {vlan_db_id})")

        old_members = self.vpm_repo.find_by_vlan_id(vlan_db_id)
        old_port_ids = [m.port_id for m in old_members]
        if old_port_ids:
            self.port_repo.clear_vlan_by_port_ids_and_vlan(old_port_ids, str(vlan.vlan_id))

        self.vpm_repo.delete_by_vlan_id(vlan_db_id)
        if port_ids:
            self.vlan_repo.session.bulk_insert_mappings(VLANPortMember, [
                {"vlan_id": vlan_db_id, "port_id": pid, "port_mode": "access"}
                for pid in port_ids
            ])
            self.port_repo.set_vlan_by_port_ids(port_ids, str(vlan.vlan_id))

        affected_port_names = []
        all_port_ids = list(set(old_port_ids + port_ids))
        if all_port_ids:
            ports = self.port_repo.find_by_ids(all_port_ids)
            affected_port_names = [p.port_name for p in ports]

        emit_resource_change(
            vlan.device_id, OpType.VLAN_MEMBER_SET,
            affected_ports=affected_port_names,
            affected_vlans=[vlan_db_id],
        )
        logger.info("更新 VLAN 成员 vlan_db_id=%d member_count=%d", vlan_db_id, len(port_ids))


    def create_lag(self, device_id: int, data: Dict) -> LinkAggregationGroup:
        data["device_id"] = device_id

        lag_name = data.get("lag_name")
        if lag_name:
            existing = self.lag_repo.find_by_device_and_name(device_id, lag_name)
            if existing:
                raise ValidationError(f"聚合组 {lag_name} 在该设备已存在")

        lag = self.lag_repo.create(data)

        emit_resource_change(
            device_id, OpType.LAG_CREATE,
            affected_lags=[lag.id],
        )
        logger.info("创建 LAG device=%d lag_name=%s", device_id, lag.lag_name)
        return lag

    def update_lag(self, lag_id: int, data: Dict) -> LinkAggregationGroup:
        lag = self.lag_repo.find_by_id(lag_id)
        if not lag:
            raise ValidationError(f"LAG 不存在 (ID: {lag_id})")

        allowed = {"purpose", "lag_type", "algorithm", "status"}
        for key, value in data.items():
            if key in allowed:
                setattr(lag, key, value)

        emit_resource_change(
            lag.device_id, OpType.LAG_UPDATE,
            affected_lags=[lag_id],
        )
        logger.info("更新 LAG lag_id=%d", lag_id)
        return lag

    def delete_lag(self, lag_id: int) -> bool:
        lag = self.lag_repo.find_by_id(lag_id)
        if not lag:
            raise ValidationError(f"LAG 不存在 (ID: {lag_id})")

        device_id = lag.device_id

        member_ports = self.port_repo.find_ports_by_lag_group_id(lag_id)
        affected_port_names = [p.port_name for p in member_ports]

        self.port_repo.clear_lag_group_id(lag_id)

        self.lag_repo.session.delete(lag)

        emit_resource_change(
            device_id, OpType.LAG_DELETE,
            affected_ports=affected_port_names,
            affected_lags=[lag_id],
        )
        logger.info("删除 LAG lag_id=%d", lag_id)
        return True

    def update_lag_members(self, lag_id: int, port_ids: List[int]) -> None:
        lag = self.lag_repo.find_by_id(lag_id)
        if not lag:
            raise ValidationError(f"LAG 不存在 (ID: {lag_id})")

        old_members = self.port_repo.find_ports_by_lag_group_id(lag_id)
        old_port_names = [p.port_name for p in old_members]

        self.port_repo.clear_lag_group_id(lag_id)

        if port_ids:
            self.port_repo.set_lag_group_id(port_ids, lag_id)

        lag.member_count = len(port_ids)

        new_port_names = []
        if port_ids:
            new_ports = self.port_repo.find_by_ids(port_ids)
            new_port_names = [p.port_name for p in new_ports]

        affected_port_names = list(set(old_port_names + new_port_names))
        emit_resource_change(
            lag.device_id, OpType.LAG_MEMBER_SET,
            affected_ports=affected_port_names,
            affected_lags=[lag_id],
        )
        logger.info("更新 LAG 成员 lag_id=%d member_count=%d", lag_id, len(port_ids))


    def create_d2n_connection(self, device_id: int, data: Dict) -> int:
        from app.services.device_connection_service import device_connection_service

        data.setdefault("device_id", device_id)
        connection_id = device_connection_service.create_connection(data)

        affected_port_names = []
        switch_port_id = data.get("switch_port_id")
        if switch_port_id:
            port = self.port_repo.find_by_id_orm(switch_port_id)
            if port:
                affected_port_names.append(port.port_name)

        emit_resource_change(
            device_id, OpType.CONNECTION_CREATE,
            affected_ports=affected_port_names,
            affected_connections=[connection_id],
        )
        logger.info("创建 D2N 连接 device=%d conn_id=%d", device_id, connection_id)
        return connection_id

    def delete_connection(self, conn_id: int, conn_type: str = "d2n") -> bool:
        from app.services.device_connection_service import device_connection_service

        affected_port_names = []
        device_id = None

        if conn_type == "n2n":
            conn = self.n2n_repo.find_by_id_for_update_orm(conn_id)
            if not conn:
                raise ValidationError(f"N2N 连接不存在 (ID: {conn_id})")

            local_port = self.port_repo.find_by_id_orm(conn.local_port_id)
            peer_port = self.port_repo.find_by_id_orm(conn.peer_port_id)
            if local_port:
                affected_port_names.append(local_port.port_name)
                device_id = local_port.device_id
            if peer_port:
                affected_port_names.append(peer_port.port_name)
                if device_id is None:
                    device_id = peer_port.device_id

            result = device_connection_service.delete_network_connection_by_id(conn_id)
        else:
            conn = self.conn_repo.find_by_id(conn_id)
            if not conn:
                raise ValidationError(f"D2N 连接不存在 (ID: {conn_id})")

            device_id = conn.get("device_id")
            switch_port_id = conn.get("switch_port_id")
            if switch_port_id:
                port = self.port_repo.find_by_id_orm(switch_port_id)
                if port:
                    affected_port_names.append(port.port_name)

            result = device_connection_service.delete_connection(conn_id)

        if result and device_id:
            emit_resource_change(
                device_id, OpType.CONNECTION_DELETE,
                affected_ports=affected_port_names,
                affected_connections=[conn_id],
            )
        logger.info("删除连接 conn_id=%d type=%s", conn_id, conn_type)
        return result


port_management_service = PortManagementService(
    port_repo=NetworkPortRepository(),
    vlan_repo=VLANRepository(),
    vpm_repo=VLANPortMemberRepository(),
    lag_repo=LinkAggregationRepository(),
    conn_repo=DeviceConnectionRepository(),
    n2n_repo=NetworkConnectionRepository(),
)
