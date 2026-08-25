# -*- coding: utf-8 -*-
"""
网络设备间连接 Repository（N2N）

提供 network_connections 表的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.models.network_connection import NetworkConnection
from app.persistence.base import SQLAlchemyRepository
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)

class NetworkConnectionRepository(SQLAlchemyRepository):

    def __init__(self, session=None):
        super().__init__(NetworkConnection, session)


    def find_by_id(self, conn_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(NetworkConnection.id == conn_id)
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找N2N连接失败", original_error=e)

    def find_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        try:
            conns = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(
                    or_(
                        NetworkConnection.local_device_id == device_id,
                        NetworkConnection.peer_device_id == device_id,
                    )
                )
                .all()
            )
            return [c.to_dict(perspective_device_id=device_id) for c in conns]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查询设备N2N连接失败", original_error=e)

    def find_by_port(self, port_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = (
                self.session.query(NetworkConnection)
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                    joinedload(NetworkConnection.local_device),
                    joinedload(NetworkConnection.peer_device),
                )
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接失败", original_error=e)

    def find_by_port_ids_orm(self, port_ids: list[int]) -> list[NetworkConnection]:
        if not port_ids:
            return []
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id.in_(port_ids),
                        NetworkConnection.peer_port_id.in_(port_ids),
                    )
                )
                .options(
                    joinedload(NetworkConnection.local_port),
                    joinedload(NetworkConnection.peer_port),
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口列表查找N2N连接失败", original_error=e)

    def find_by_port_for_update(self, port_id: int) -> Optional[Dict[str, Any]]:
        try:
            conn = (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .with_for_update()
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接(加锁)失败", original_error=e)

    def find_by_port_for_update_orm(self, port_id: int) -> Optional[NetworkConnection]:
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == port_id,
                        NetworkConnection.peer_port_id == port_id,
                    )
                )
                .with_for_update()
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据端口查找N2N连接(加锁ORM)失败", original_error=e)

    def find_by_id_for_update_orm(self, conn_id: int) -> Optional[NetworkConnection]:
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(NetworkConnection.id == conn_id)
                .with_for_update()
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("根据ID查找N2N连接(加锁ORM)失败", original_error=e)

    def find_existing_by_ports_orm(self, local_port_id: int, peer_port_id: int) -> Optional[NetworkConnection]:
        try:
            return (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == local_port_id,
                        NetworkConnection.peer_port_id == local_port_id,
                        NetworkConnection.local_port_id == peer_port_id,
                        NetworkConnection.peer_port_id == peer_port_id,
                    )
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找已有N2N连接(ORM)失败", original_error=e)

    def exists_by_ports(self, local_port_id: int, peer_port_id: int) -> bool:
        try:
            return self.session.query(NetworkConnection).filter(
                or_(
                    (NetworkConnection.local_port_id == local_port_id) & (NetworkConnection.peer_port_id == peer_port_id),
                    (NetworkConnection.local_port_id == peer_port_id) & (NetworkConnection.peer_port_id == local_port_id),
                )
            ).first() is not None
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查N2N连接存在性失败", original_error=e)


    def create_connection(self, data: Dict[str, Any]) -> int:
        try:
            local_port_id = data.get("local_port_id")
            peer_port_id  = data.get("peer_port_id")

            existing = (
                self.session.query(NetworkConnection)
                .filter(
                    or_(
                        NetworkConnection.local_port_id == local_port_id,
                        NetworkConnection.peer_port_id == local_port_id,
                        NetworkConnection.local_port_id == peer_port_id,
                        NetworkConnection.peer_port_id == peer_port_id,
                    )
                )
                .first()
            )

            if existing:
                existing.local_port_id = local_port_id
                existing.peer_port_id  = peer_port_id
                existing.local_device_id = data.get("local_device_id")
                existing.peer_device_id  = data.get("peer_device_id")
                for field in ("connection_type", "vlan_id", "status", "notes",
                              "bandwidth", "description", "lag_group_id"):
                    if field in data:
                        setattr(existing, field, data[field])
                self.session.flush()
                return existing.id

            conn = NetworkConnection(
                local_port_id=local_port_id,
                peer_port_id=peer_port_id,
                local_device_id=data.get("local_device_id"),
                peer_device_id=data.get("peer_device_id"),
                connection_type=data.get("connection_type"),
                vlan_id=data.get("vlan_id"),
                status=data.get("status", "active"),
                notes=data.get("notes"),
                bandwidth=data.get("bandwidth"),
                description=data.get("description"),
                lag_group_id=data.get("lag_group_id"),
            )
            self.session.add(conn)
            self.session.flush()
            return conn.id
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建N2N连接失败", original_error=e)

    def update_connection(self, conn_id: int, data: Dict[str, Any]) -> bool:
        try:
            conn = self.session.query(NetworkConnection).filter(
                NetworkConnection.id == conn_id
            ).first()
            if not conn:
                return False

            allowed = {
                "connection_type", "vlan_id", "status", "notes",
                "bandwidth", "description", "lag_group_id",
            }
            for field in allowed:
                if field in data:
                    setattr(conn, field, data[field])

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新N2N连接失败", original_error=e)

    def delete_connection_orm(self, conn: "NetworkConnection") -> None:
        try:
            self.session.delete(conn)
            self.session.flush()
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除N2N连接(ORM)失败", original_error=e)

    def delete_connection(self, conn_id: int) -> bool:
        try:
            conn = self.session.query(NetworkConnection).filter(
                NetworkConnection.id == conn_id
            ).first()
            if not conn:
                return False
            self.session.delete(conn)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除N2N连接失败", original_error=e)

    def delete_by_device(self, device_id: int) -> int:
        try:
            count = self.session.query(NetworkConnection).filter(
                or_(
                    NetworkConnection.local_device_id == device_id,
                    NetworkConnection.peer_device_id == device_id,
                )
            ).delete(synchronize_session=False)
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备N2N连接失败", original_error=e)
