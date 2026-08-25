# -*- coding: utf-8 -*-
"""
设备连接Repository

变更记录:
  - [Fix #5] create_connection / update_connection: 补充 device_nics_port_id 字段，
             原实现静默丢弃该字段，导致 NIC 端口关联永远为 NULL
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from app.models.device_connection import DeviceConnection
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)


class DeviceConnectionRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """设备连接Repository"""

    def __init__(self, session=None):
        super().__init__(DeviceConnection, session)


    @staticmethod
    def _default_options():
        """默认 joinedload 选项"""
        return [
            joinedload(DeviceConnection.device),
            joinedload(DeviceConnection.switch_device),
            joinedload(DeviceConnection.switch_port),
            joinedload(DeviceConnection.nics_port),
        ]


    def find_by_id(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """根据连接 ID 查找"""
        try:
            conn = (
                self.session.query(DeviceConnection)
                .options(*self._default_options())
                .filter(DeviceConnection.id == connection_id)
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备连接失败", original_error=e)

    def find_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        """根据设备 ID 查找连接列表"""
        try:
            conns = (
                self.session.query(DeviceConnection)
                .options(*self._default_options())
                .filter(DeviceConnection.device_id == device_id)
                .all()
            )
            return [c.to_dict() for c in conns]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备连接失败", original_error=e)

    def find_by_switch_device(self, switch_device_id: int) -> List[Dict[str, Any]]:
        """根据交换机设备 ID 查找连接列表"""
        try:
            conns = (
                self.session.query(DeviceConnection)
                .options(*self._default_options())
                .filter(DeviceConnection.switch_device_id == switch_device_id)
                .all()
            )
            return [c.to_dict() for c in conns]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备连接失败", original_error=e)

    def find_by_switch_and_port(
        self, switch_device_id: int, switch_port_id: int
    ) -> Optional[Dict[str, Any]]:
        """根据交换机+端口精确查找连接"""
        try:
            conn = (
                self.session.query(DeviceConnection)
                .filter(
                    DeviceConnection.switch_device_id == switch_device_id,
                    DeviceConnection.switch_port_id == switch_port_id,
                )
                .first()
            )
            return conn.to_dict() if conn else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备连接失败", original_error=e)

    def exists_connection(
        self,
        device_id: int,
        switch_device_id: int,
        switch_port_id: int = None,
    ) -> bool:
        """检查连接是否存在"""
        try:
            q = self.session.query(DeviceConnection).filter(
                DeviceConnection.device_id == device_id,
                DeviceConnection.switch_device_id == switch_device_id,
            )
            if switch_port_id is not None:
                q = q.filter(DeviceConnection.switch_port_id == switch_port_id)
            return self.session.query(q.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查连接存在性失败", original_error=e)

    def exists_connection_for_update(
        self,
        device_id: int,
        switch_device_id: int,
        switch_port_id: int = None,
    ) -> bool:
        """检查连接是否存在（使用 SELECT FOR UPDATE 行级锁，防止并发竞态）

        在 create_connection 的事务内调用，确保两个并发请求不会同时通过
        存在性检查后创建重复连接。
        """
        try:
            q = self.session.query(DeviceConnection).filter(
                DeviceConnection.device_id == device_id,
                DeviceConnection.switch_device_id == switch_device_id,
            )
            if switch_port_id is not None:
                q = q.filter(DeviceConnection.switch_port_id == switch_port_id)
            return q.with_for_update().first() is not None
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查连接存在性失败(locked)", original_error=e)

    def count_by_device(self, device_id: int) -> int:
        """统计设备的连接数量"""
        try:
            return (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.device_id == device_id)
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计连接数量失败", original_error=e)

    def count_by_switch(self, switch_device_id: int) -> int:
        """统计交换机的连接数量"""
        try:
            return (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.switch_device_id == switch_device_id)
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计连接数量失败", original_error=e)


    def create_connection(self, data: Dict[str, Any]) -> int:
        """创建设备连接，返回新连接 ID（flush，由 Service 统一 commit）"""
        try:
            conn = DeviceConnection(
                device_id=data.get("device_id"),
                switch_device_id=data.get("switch_device_id"),
                switch_port_id=data.get("switch_port_id"),
                device_nics_port_id=data.get("device_nics_port_id"),
                connection_type=data.get("connection_type"),
                vlan_id=data.get("vlan_id"),
                vlan_mode=data.get("vlan_mode", "access"),
                native_vlan=data.get("native_vlan"),
                status=data.get("status", "active"),
                notes=data.get("notes") or data.get("remark"),
            )
            self.session.add(conn)
            self.session.flush()
            return conn.id
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建设备连接失败", original_error=e)

    def update_connection(self, connection_id: int, data: Dict[str, Any]) -> bool:
        """更新设备连接，返回是否成功（flush，由 Service 统一 commit）"""
        try:
            conn = (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.id == connection_id)
                .first()
            )
            if not conn:
                return False

            allowed = {
                "device_id", "switch_device_id", "switch_port_id",
                "device_nics_port_id",
                "connection_type", "vlan_id", "vlan_mode",
                "native_vlan",
                "notes", "status",
            }
            for field in allowed:
                if field in data:
                    setattr(conn, field, data[field])

            if "remark" in data and "notes" not in data:
                conn.notes = data["remark"]

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新设备连接失败", original_error=e)

    def delete_connection(self, connection_id: int) -> bool:
        """删除单条连接（flush，由 Service 统一 commit）"""
        try:
            conn = (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.id == connection_id)
                .first()
            )
            if not conn:
                return False
            self.session.delete(conn)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备连接失败", original_error=e)

    def delete_device_connections(self, device_id: int) -> int:
        """删除设备的全部连接，返回删除数量（flush，由 Service 统一 commit）

        警告：此方法不自动释放端口，调用方（Service 层）须先释放端口再调用此方法。
        """
        try:
            count = (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.device_id == device_id)
                .delete(synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备连接失败", original_error=e)

    def delete_switch_connections(self, switch_device_id: int) -> int:
        """删除交换机的全部连接，返回删除数量（flush，由 Service 统一 commit）

        警告：此方法不自动释放端口，调用方须先释放端口。
        """
        try:
            count = (
                self.session.query(DeviceConnection)
                .filter(DeviceConnection.switch_device_id == switch_device_id)
                .delete(synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除交换机连接失败", original_error=e)
