# -*- coding: utf-8 -*-
"""
设备存储Repository（新增）

将 DeviceStorageService 中的裸 SQL 迁移至此，与其他模块保持一致的 Repository 模式。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.models.device_storage import DeviceStorage
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)


class DeviceStorageRepository(SQLAlchemyRepository, QueryOptimizationMixin):

    def __init__(self, session=None):
        super().__init__(DeviceStorage, session)


    def device_exists(self, device_id: int) -> bool:
        try:
            from app.models.device import Device
            from app.core.enums import DeviceStatus

            result = (
                self.session.query(Device.id)
                .filter(
                    Device.id == device_id,
                    Device.status != DeviceStatus.SCRAPPED,
                    Device.deleted_at.is_(None),
                )
                .first()
            )
            return result is not None
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查设备存在性失败", original_error=e)

    def find_by_device(self, device_id: int) -> List[DeviceStorage]:
        try:
            return (
                self.session.query(DeviceStorage)
                .filter(DeviceStorage.device_id == device_id)
                .order_by(DeviceStorage.id)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备存储失败", original_error=e)

    def find_grouped_by_device(self, device_id: int) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.session.query(
                    DeviceStorage.storage_type,
                    DeviceStorage.capacity,
                    DeviceStorage.interface_type,
                    DeviceStorage.manufacturer,
                    DeviceStorage.model,
                    func.count(DeviceStorage.id).label("total_count"),
                    func.group_concat(
                        DeviceStorage.serial_number.op("ORDER BY")(DeviceStorage.serial_number)
                    ).label("serial_numbers"),
                )
                .filter(DeviceStorage.device_id == device_id)
                .group_by(
                    DeviceStorage.storage_type,
                    DeviceStorage.capacity,
                    DeviceStorage.interface_type,
                    DeviceStorage.manufacturer,
                    DeviceStorage.model,
                )
                .all()
            )

            result = []
            for row in rows:
                item = {
                    "storage_type": row.storage_type,
                    "capacity": row.capacity,
                    "interface_type": row.interface_type,
                    "manufacturer": row.manufacturer,
                    "model": row.model,
                    "total_count": int(row.total_count or 0),
                    "serial_numbers": (
                        [sn for sn in row.serial_numbers.split(",") if sn]
                        if row.serial_numbers
                        else []
                    ),
                }
                result.append(item)

            return result
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找分组存储失败", original_error=e)

    def find_by_id(self, storage_id: int) -> Optional[DeviceStorage]:
        try:
            return (
                self.session.query(DeviceStorage)
                .filter(DeviceStorage.id == storage_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找存储记录失败", original_error=e)

    def serial_number_exists(
        self,
        serial_number: str,
        exclude_id: int = None,
        exclude_device_id: int = None,
    ) -> bool:
        if not serial_number:
            return False
        try:
            q = self.session.query(DeviceStorage).filter(
                DeviceStorage.serial_number == serial_number
            )
            if exclude_id:
                q = q.filter(DeviceStorage.id != exclude_id)
            if exclude_device_id:
                q = q.filter(DeviceStorage.device_id != exclude_device_id)
            return self.session.query(q.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查序列号失败", original_error=e)

    def batch_serial_numbers_exist(
        self,
        serial_numbers: List[str],
        exclude_device_id: int = None,
    ) -> List[str]:
        if not serial_numbers:
            return []
        try:
            q = self.session.query(DeviceStorage.serial_number).filter(
                DeviceStorage.serial_number.in_(serial_numbers)
            )
            if exclude_device_id:
                q = q.filter(DeviceStorage.device_id != exclude_device_id)
            return [row[0] for row in q.all()]
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量检查序列号失败", original_error=e)


    def create(self, data: Dict[str, Any]) -> DeviceStorage:
        try:
            obj = DeviceStorage(
                device_id=data["device_id"],
                storage_type=data["storage_type"],
                capacity=data["capacity"],
                capacity_gb=data.get("capacity_gb"),
                interface_type=data.get("interface_type"),
                slot_number=data.get("slot_number"),
                manufacturer=data.get("manufacturer"),
                model=data.get("model"),
                serial_number=data.get("serial_number"),
                firmware=data.get("firmware"),
                status=data.get("status", "normal"),
            )
            self.session.add(obj)
            self.session.flush()
            return obj
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建存储记录失败", original_error=e)

    def bulk_create(self, device_id: int, items: List[Dict[str, Any]]) -> int:
        try:
            objs = [
                DeviceStorage(
                    device_id=device_id,
                    storage_type=item["storage_type"],
                    capacity=item["capacity"],
                    capacity_gb=item.get("capacity_gb"),
                    interface_type=item.get("interface_type"),
                    slot_number=item.get("slot_number"),
                    manufacturer=item.get("manufacturer"),
                    model=item.get("model"),
                    serial_number=item.get("serial_number"),
                    firmware=item.get("firmware"),
                    status=item.get("status", "normal"),
                )
                for item in items
            ]
            self.session.add_all(objs)
            self.session.flush()
            return len(objs)
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量创建存储记录失败", original_error=e)

    def update(self, storage_id: int, data: Dict[str, Any]) -> bool:
        try:
            obj = self.find_by_id(storage_id)
            if not obj:
                return False

            allowed = {
                "storage_type", "capacity", "capacity_gb", "interface_type",
                "slot_number", "manufacturer", "model", "serial_number",
                "firmware", "status",
            }
            for field in allowed:
                if field in data:
                    setattr(obj, field, data[field])

            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新存储记录失败", original_error=e)

    def delete(self, storage_id: int) -> bool:
        try:
            obj = self.find_by_id(storage_id)
            if not obj:
                return False
            self.session.delete(obj)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除存储记录失败", original_error=e)

    def delete_by_device(self, device_id: int) -> int:
        try:
            count = (
                self.session.query(DeviceStorage)
                .filter(DeviceStorage.device_id == device_id)
                .delete(synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("删除设备存储失败", original_error=e)
