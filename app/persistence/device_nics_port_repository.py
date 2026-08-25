# -*- coding: utf-8 -*-
"""
设备网卡端口Repository

提供设备网卡端口相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.models.device_nics_port import DeviceNicsPort
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)


class DeviceNicsPortRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """设备网卡端口Repository"""

    def __init__(self, session=None):
        super().__init__(DeviceNicsPort, session)


    def find_by_id(self, port_id: int) -> Optional[Dict[str, Any]]:
        """根据端口ID查找,含关联设备信息
        
        Args:
            port_id: 端口ID
            
        Returns:
            端口信息字典,不存在则返回None
        """
        try:
            port = (
                self.session.query(DeviceNicsPort)
                .options(joinedload(DeviceNicsPort.device))
                .filter(DeviceNicsPort.id == port_id)
                .first()
            )
            return port.to_dict(include_relations=True) if port else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def find_ports_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        """获取设备的全部端口列表
        
        Args:
            device_id: 设备ID
            
        Returns:
            端口列表
        """
        try:
            ports = (
                self.session.query(DeviceNicsPort)
                .options(joinedload(DeviceNicsPort.device))
                .filter(DeviceNicsPort.device_id == device_id)
                .order_by(DeviceNicsPort.nic_number, DeviceNicsPort.port_number)
                .all()
            )
            return [p.to_dict(include_relations=True) for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口列表失败", original_error=e)

    def find_ports_by_device_orm(self, device_id: int) -> List[DeviceNicsPort]:
        """获取设备的全部端口列表（返回ORM对象，供Service层使用）

        Args:
            device_id: 设备ID

        Returns:
            端口ORM对象列表
        """
        try:
            return (
                self.session.query(DeviceNicsPort)
                .filter(DeviceNicsPort.device_id == device_id)
                .order_by(DeviceNicsPort.nic_number, DeviceNicsPort.port_number)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口列表失败", original_error=e)

    def find_by_id_orm(self, port_id: int) -> Optional[DeviceNicsPort]:
        """根据端口ID查找（返回ORM对象，find_port_by_id_orm 的别名）

        Args:
            port_id: 端口ID

        Returns:
            端口ORM对象，不存在则返回None
        """
        return self.find_port_by_id_orm(port_id)

    def find_port_by_id_orm(self, port_id: int) -> Optional[DeviceNicsPort]:
        """根据端口ID查找（返回ORM对象）

        Args:
            port_id: 端口ID

        Returns:
            端口ORM对象，不存在则返回None
        """
        try:
            return (
                self.session.query(DeviceNicsPort)
                .filter(DeviceNicsPort.id == port_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def find_ports_by_ids(self, port_ids: List[int]) -> List[DeviceNicsPort]:
        """根据ID列表批量查询端口（返回ORM对象，不限设备）

        Args:
            port_ids: 端口ID列表

        Returns:
            端口ORM对象列表（忽略不存在的ID）
        """
        if not port_ids:
            return []
        try:
            return (
                self.session.query(DeviceNicsPort)
                .filter(DeviceNicsPort.id.in_(port_ids))
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查找端口失败", original_error=e)

    def find_port_by_nic_port_orm(
        self,
        device_id: int,
        nic_number: int,
        port_number: int,
    ) -> Optional[DeviceNicsPort]:
        """根据设备ID、网卡编号和端口编号查找端口（返回ORM对象）

        Args:
            device_id: 设备ID
            nic_number: 网卡编号
            port_number: 端口编号

        Returns:
            端口ORM对象，不存在则返回None
        """
        try:
            return (
                self.session.query(DeviceNicsPort)
                .filter(
                    DeviceNicsPort.device_id == device_id,
                    DeviceNicsPort.nic_number == nic_number,
                    DeviceNicsPort.port_number == port_number,
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def find_ports_by_type_speed_orm(
        self,
        device_id: int,
        port_type: str = None,
        port_speed: str = None,
    ) -> List[DeviceNicsPort]:
        """按类型和速率筛选端口（返回ORM对象）

        Args:
            device_id: 设备ID
            port_type: 端口类型过滤(可选)
            port_speed: 端口速率过滤(可选)

        Returns:
            端口ORM对象列表
        """
        try:
            query = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.device_id == device_id
            )
            if port_type:
                query = query.filter(DeviceNicsPort.port_type == port_type)
            if port_speed:
                query = query.filter(DeviceNicsPort.port_speed == port_speed)
            return query.order_by(
                DeviceNicsPort.nic_number, DeviceNicsPort.port_number
            ).all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("按类型速率查找端口失败", original_error=e)

    def find_available_ports(
        self, 
        device_id: int, 
        port_type: str = None, 
        port_speed: str = None
    ) -> List[Dict[str, Any]]:
        """获取空闲端口(status='free')
        
        Args:
            device_id: 设备ID
            port_type: 端口类型过滤(可选)
            port_speed: 端口速率过滤(可选)
            
        Returns:
            空闲端口列表
        """
        try:
            query = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.device_id == device_id,
                DeviceNicsPort.port_status == 'free'
            )
            
            if port_type:
                query = query.filter(DeviceNicsPort.port_type == port_type)
            if port_speed:
                query = query.filter(DeviceNicsPort.port_speed == port_speed)
            
            ports = query.order_by(
                DeviceNicsPort.nic_number, 
                DeviceNicsPort.port_number
            ).all()
            
            return [p.to_dict() for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找可用端口失败", original_error=e)

    def find_active_ports(self, device_id: int) -> List[Dict[str, Any]]:
        """获取有效端口(排除disabled),用于容量计算
        
        Args:
            device_id: 设备ID
            
        Returns:
            有效端口列表
        """
        try:
            ports = (
                self.session.query(DeviceNicsPort)
                .filter(
                    DeviceNicsPort.device_id == device_id,
                    DeviceNicsPort.port_status != 'disabled',
                )
                .all()
            )
            return [p.to_dict() for p in ports]
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找有效端口失败", original_error=e)

    def find_port_by_nic_port(
        self, 
        device_id: int, 
        nic_number: int, 
        port_number: int
    ) -> Optional[Dict[str, Any]]:
        """根据设备ID、网卡编号和端口编号查找端口
        
        Args:
            device_id: 设备ID
            nic_number: 网卡编号
            port_number: 端口编号
            
        Returns:
            端口信息字典,不存在则返回None
        """
        try:
            port = (
                self.session.query(DeviceNicsPort)
                .options(joinedload(DeviceNicsPort.device))
                .filter(
                    DeviceNicsPort.device_id == device_id,
                    DeviceNicsPort.nic_number == nic_number,
                    DeviceNicsPort.port_number == port_number,
                )
                .first()
            )
            return port.to_dict(include_relations=True) if port else None
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找端口失败", original_error=e)

    def count_ports_by_device(self, device_id: int, filters: Dict = None) -> int:
        """统计端口数量,可按status过滤
        
        Args:
            device_id: 设备ID
            filters: 过滤条件,如{'status': 'free'}
            
        Returns:
            端口数量
        """
        try:
            q = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.device_id == device_id
            )
            if filters:
                if 'status' in filters:
                    q = q.filter(DeviceNicsPort.port_status == filters['status'])
                if 'port_type' in filters:
                    q = q.filter(DeviceNicsPort.port_type == filters['port_type'])
                if 'port_speed' in filters:
                    q = q.filter(DeviceNicsPort.port_speed == filters['port_speed'])
            return q.count()
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计端口数量失败", original_error=e)


    def create_ports_batch(self, device_id: int, ports: List[Dict]) -> int:
        """批量创建端口,先清除该设备已有端口再创建,返回创建数量

        注意：仅 flush，由调用方（Service/Route）统一 commit。

        如果设备已有端口且存在关联的连接记录（DeviceConnection），
        则拒绝操作以防止级联删除连接历史，调用方应先手动处理连接。

        Args:
            device_id: 设备ID
            ports: 端口数据列表

        Returns:
            创建的端口数量

        Raises:
            QueryExecutionError: 已有关联连接时拒绝操作
        """
        try:
            from app.models.device_connection import DeviceConnection
            existing_ports = (
                self.session.query(DeviceNicsPort)
                .filter(DeviceNicsPort.device_id == device_id)
                .all()
            )
            if existing_ports:
                existing_port_ids = [p.id for p in existing_ports]
                connection_count = (
                    self.session.query(DeviceConnection)
                    .filter(DeviceConnection.device_nics_port_id.in_(existing_port_ids))
                    .count()
                )
                if connection_count > 0:
                    raise QueryExecutionError(
                        f"设备 {device_id} 已有 {connection_count} 条关联连接记录，"
                        "请先处理连接后再重新同步端口，避免丢失连接历史"
                    )

            self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.device_id == device_id
            ).delete()

            objs = [
                DeviceNicsPort(
                    device_id=device_id,
                    nic_number=p.get('nic_number'),
                    port_number=p.get('port_number'),
                    port_name=p.get('port_name'),
                    port_type=p.get('port_type'),
                    port_speed=p.get('port_speed'),
                    port_status=p.get('port_status', 'free'),
                    description=p.get('description'),
                )
                for p in ports
            ]
            self.session.add_all(objs)
            self.session.flush()
            return len(objs)
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量创建端口失败", original_error=e)

    def update_port(self, port_id: int, data: Dict[str, Any]) -> bool:
        """更新端口字段（仅 flush，由调用方统一 commit）"""
        try:
            port = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.id == port_id
            ).first()

            if not port:
                return False

            allowed = {
                'nic_number', 'port_number', 'port_name',
                'port_type', 'port_speed', 'port_status',
                'description',
            }
            for field in allowed:
                if field in data:
                    setattr(port, field, data[field])

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新端口失败", original_error=e)

    def occupy_port(self, port_id: int) -> bool:
        """占用 NIC 端口（仅 flush，由调用方统一 commit）"""
        try:
            port = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.id == port_id
            ).first()
            if not port:
                return False
            port.occupy()
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("占用NIC端口失败", original_error=e)

    def release_port(self, port_id: int) -> bool:
        """释放 NIC 端口（仅 flush，由调用方统一 commit）"""
        try:
            port = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.id == port_id
            ).first()
            if not port:
                return False
            port.release()
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("释放NIC端口失败", original_error=e)

    def update_port_status(self, port_id: int, status: str) -> bool:
        """更新端口状态（仅 flush，由调用方统一 commit）"""
        try:
            port = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.id == port_id
            ).first()

            if not port:
                return False

            port.port_status = status
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新端口状态失败", original_error=e)

    def delete_port(self, port_id: int) -> bool:
        """删除单个端口（仅 flush，由调用方统一 commit）"""
        try:
            port = self.session.query(DeviceNicsPort).filter(
                DeviceNicsPort.id == port_id
            ).first()

            if not port:
                return False

            self.session.delete(port)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除端口失败", original_error=e)

    def delete_device_ports(self, device_id: int) -> int:
        """删除设备全部端口,返回删除数量（仅 flush，由调用方统一 commit）"""
        try:
            count = (
                self.session.query(DeviceNicsPort)
                .filter(DeviceNicsPort.device_id == device_id)
                .delete(synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备端口失败", original_error=e)
