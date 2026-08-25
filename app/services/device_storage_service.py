# -*- coding: utf-8 -*-
"""
设备存储服务模块

所有数据访问通过 DeviceStorageRepository 完成，不再直接执行 SQL。
序列号校验统一使用批量查询，避免 N 次单条查询。
"""
from app.utils.logging import get_logger
from typing import Dict, List

from app.persistence.device_storage_repository import DeviceStorageRepository
from app.persistence.device_repository import DeviceRepository
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)


class DeviceStorageService:

    def __init__(self, storage_repository: DeviceStorageRepository):
        self.storage_repo = storage_repository


    def get_device_storage(self, device_id: int, grouped: bool = True) -> List[Dict]:
        self._assert_device_exists(device_id)

        if grouped:
            return self.storage_repo.find_grouped_by_device(device_id)
        else:
            return [s.to_dict() for s in self.storage_repo.find_by_device(device_id)]


    def add_device_storage(
        self,
        device_id: int,
        storage_type: str = "",
        capacity: str = "",
        count: int = 1,
        interface_type: str = None,
        manufacturer: str = None,
        model: str = None,
        serial_number: str = None,
        storage_list: List[Dict] = None,
        template_id: int = None,
    ) -> bool:
        self._assert_device_exists(device_id)

        if template_id:
            from app.services.device_service import DeviceService, _format_capacity
            svc = DeviceService(DeviceRepository())
            tpl = svc._resolve_component_template(template_id, "disk")
            spec = tpl.get("spec") or {}
            storage_type   = storage_type   or spec.get("storage_type", "") or spec.get("type", "")
            interface_type = interface_type or spec.get("interface_type") or spec.get("interface")
            manufacturer   = manufacturer   or tpl.get("brand")
            model          = model          or tpl.get("model")
            capacity_gb    = spec.get("capacity_gb")
            if not capacity and capacity_gb:
                capacity = _format_capacity(capacity_gb)
            if not capacity:
                capacity = spec.get("capacity", "")

        if storage_list:
            sns = [item.get("serial_number") for item in storage_list if item.get("serial_number")]
            if sns:
                duplicates = self.storage_repo.batch_serial_numbers_exist(sns)
                if duplicates:
                    raise ValidationError(f"序列号已存在: {duplicates}")

            normalized = [
                {
                    "storage_type": item.get("storage_type", storage_type),
                    "capacity": item.get("capacity", capacity),
                    "interface_type": item.get("interface_type", interface_type),
                    "manufacturer": item.get("manufacturer", manufacturer),
                    "model": item.get("model", model),
                    "serial_number": item.get("serial_number"),
                }
                for item in storage_list
            ]
            n = self.storage_repo.bulk_create(device_id, normalized)
            logger.info(f"为设备 {device_id} 批量添加 {n} 块硬盘")
            return True

        if serial_number and self.storage_repo.serial_number_exists(serial_number):
            raise ValidationError(f"序列号 {serial_number} 已存在")

        items = [
            {
                "storage_type": storage_type,
                "capacity": capacity,
                "interface_type": interface_type,
                "manufacturer": manufacturer,
                "model": model,
                "serial_number": serial_number,
            }
            for _ in range(count)
        ]
        self.storage_repo.bulk_create(device_id, items)
        logger.info(f"为设备 {device_id} 添加 {count} 块硬盘")
        return True


    def update_device_storage(
        self,
        storage_id: int,
        storage_type: str = None,
        capacity: str = None,
        interface_type: str = None,
        manufacturer: str = None,
        model: str = None,
        serial_number: str = None,
    ) -> bool:
        obj = self.storage_repo.find_by_id(storage_id)
        if not obj:
            raise ValidationError(f"硬盘不存在 (ID: {storage_id})")

        if serial_number and self.storage_repo.serial_number_exists(
            serial_number, exclude_id=storage_id
        ):
            raise ValidationError(f"序列号 {serial_number} 已存在")

        data = {}
        for field, val in {
            "storage_type": storage_type,
            "capacity": capacity,
            "interface_type": interface_type,
            "manufacturer": manufacturer,
            "model": model,
            "serial_number": serial_number,
        }.items():
            if val is not None:
                data[field] = val

        if not data:
            return True

        result = self.storage_repo.update(storage_id, data)
        logger.info(f"更新硬盘 {storage_id} 成功")
        return result

    def update_device_storage_config(
        self, device_id: int, storage_config: List[Dict]
    ) -> bool:
        self._assert_device_exists(device_id)

        if storage_config:
            sns = [item.get("serial_number") for item in storage_config if item.get("serial_number")]
            if sns:
                duplicates = self.storage_repo.batch_serial_numbers_exist(
                    sns, exclude_device_id=device_id
                )
                if duplicates:
                    raise ValidationError(f"以下序列号已被其他设备使用: {duplicates}")

        deleted = self.storage_repo.delete_by_device(device_id)
        logger.info(f"删除设备 {device_id} 旧硬盘记录 {deleted} 条")

        if storage_config:
            self.storage_repo.bulk_create(device_id, storage_config)
            logger.info(f"写入设备 {device_id} 新硬盘记录 {len(storage_config)} 条")

        self.storage_repo.session.flush()

        return True


    def delete_device_storage(self, storage_id: int) -> bool:
        obj = self.storage_repo.find_by_id(storage_id)
        if not obj:
            raise ValidationError(f"硬盘不存在 (ID: {storage_id})")

        result = self.storage_repo.delete(storage_id)
        logger.info(f"删除硬盘 {storage_id} 成功")
        return result

    def delete_device_storage_by_device_id(self, device_id: int) -> int:
        count = self.storage_repo.delete_by_device(device_id)
        logger.info(f"删除设备 {device_id} 的全部硬盘，共 {count} 条")
        return count

    def batch_delete_storage(self, storage_ids: List[int]) -> Dict:
        if not storage_ids:
            return {"deleted": [], "not_found": []}

        deleted: List[int] = []
        not_found: List[int] = []
        for sid in storage_ids:
            obj = self.storage_repo.find_by_id(sid)
            if not obj:
                not_found.append(sid)
                continue
            self.storage_repo.delete(sid)
            deleted.append(sid)
        self.storage_repo.session.flush()
        return {"deleted": deleted, "not_found": not_found}


    def validate_serial_number(
        self, serial_number: str, exclude_id: int = None
    ) -> Dict:
        if not serial_number:
            return {"is_valid": True, "is_duplicate": False, "message": "序列号为空，校验通过"}

        is_dup = self.storage_repo.serial_number_exists(serial_number, exclude_id=exclude_id)
        return {
            "is_valid": not is_dup,
            "is_duplicate": is_dup,
            "message": "序列号已存在" if is_dup else "序列号可用",
        }


    def _assert_device_exists(self, device_id: int) -> None:
        if not self.storage_repo.device_exists(device_id):
            raise ValidationError(f"设备不存在 (ID: {device_id})")


device_storage_service = DeviceStorageService(DeviceStorageRepository())
