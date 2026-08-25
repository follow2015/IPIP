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
    """设备存储服务类

    职责：硬盘的增删改查及序列号唯一性校验。
    数据访问：全部通过 DeviceStorageRepository。
    """

    def __init__(self, storage_repository: DeviceStorageRepository):
        self.storage_repo = storage_repository


    def get_device_storage(self, device_id: int, grouped: bool = True) -> List[Dict]:
        """获取设备硬盘列表

        Args:
            device_id: 设备 ID
            grouped: True 返回按型号分组聚合结果；False 返回每条物理记录

        Raises:
            ValidationError: 设备不存在时抛出
        """
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
        """为设备添加硬盘，支持批量添加

        Args:
            device_id: 设备 ID
            storage_type: 存储类型（当 storage_list 为空时必传）
            capacity: 容量（当 storage_list 为空时必传）
            count: 单类硬盘数量（创建 count 条记录，每条 count=1）
            interface_type / manufacturer / model / serial_number: 可选硬件参数
            storage_list: 批量添加列表，列表中每项可覆盖默认参数
            template_id: 配件模板ID，从模板自动填充缺失字段

        Returns:
            bool: 添加成功返回 True

        Raises:
            ValidationError: 设备不存在或序列号重复
        """
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
        """更新单条硬盘信息

        Raises:
            ValidationError: 硬盘不存在或序列号重复
        """
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
        """整机覆盖写入硬盘配置（先删后增，事务内操作）

        使用 flush() 替代 begin_nested() savepoint，
        由 API 层 @transactional 统一管理事务提交/回滚。

        校验逻辑：所有序列号必须在其他设备上不存在（单次批量查询）。

        Raises:
            ValidationError: 设备不存在或序列号被其他设备占用
        """
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
        """删除单条硬盘记录

        Raises:
            ValidationError: 硬盘不存在
        """
        obj = self.storage_repo.find_by_id(storage_id)
        if not obj:
            raise ValidationError(f"硬盘不存在 (ID: {storage_id})")

        result = self.storage_repo.delete(storage_id)
        logger.info(f"删除硬盘 {storage_id} 成功")
        return result

    def delete_device_storage_by_device_id(self, device_id: int) -> int:
        """删除设备全部硬盘记录

        Returns:
            int: 删除数量
        """
        count = self.storage_repo.delete_by_device(device_id)
        logger.info(f"删除设备 {device_id} 的全部硬盘，共 {count} 条")
        return count

    def batch_delete_storage(self, storage_ids: List[int]) -> Dict:
        """批量删除硬盘记录（替代前端 for(id) { DELETE /storage/<id> } 串行循环）

        不存在的 ID 标记为 not_found，其余删除。

        返回 { 'deleted': [id...], 'not_found': [id...] }

        注：仅 flush，由 API 层 @transactional 统一提交/回滚。
        """
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
        """校验序列号唯一性（供前端实时校验接口使用）

        Returns:
            Dict: {"is_valid": bool, "is_duplicate": bool, "message": str}
        """
        if not serial_number:
            return {"is_valid": True, "is_duplicate": False, "message": "序列号为空，校验通过"}

        is_dup = self.storage_repo.serial_number_exists(serial_number, exclude_id=exclude_id)
        return {
            "is_valid": not is_dup,
            "is_duplicate": is_dup,
            "message": "序列号已存在" if is_dup else "序列号可用",
        }


    def _assert_device_exists(self, device_id: int) -> None:
        """断言设备存在（非报废），不存在则抛 ValidationError"""
        if not self.storage_repo.device_exists(device_id):
            raise ValidationError(f"设备不存在 (ID: {device_id})")


device_storage_service = DeviceStorageService(DeviceStorageRepository())
