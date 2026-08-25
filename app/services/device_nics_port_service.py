# -*- coding: utf-8 -*-
"""
设备网卡端口服务 — 重构版

修复：
  1. batch_create_ports：db.session.commit() → begin_nested() savepoint，
     与项目其他 Service 保持一致，由外层事务统一提交。
  2. create_or_update_nics：filters={"status":"occupied"} → {"port_status":"occupied"}，
     修正与 model 字段名不一致的问题。
  3. batch_create_for_devices：新增方法，
     支持为多个设备（如机箱的全部子节点）一次性创建相同 NIC 端口，
     替代 AddDevicesModal / DeviceForm 中 for(nodeId) { POST /nics } 的串行循环。
"""
from app.utils.logging import get_logger
from typing import Dict, List, Optional, Tuple

from app.models.device import Device
from app.models.device_nics_port import DeviceNicsPort
from app.persistence.device_nics_port_repository import DeviceNicsPortRepository
from app.utils.nic_validator import NicValidator

logger = get_logger(__name__)


class DeviceNicsPortService:

    def __init__(self, repository: DeviceNicsPortRepository, device_repo=None):
        self.repo = repository
        self._device_repo = device_repo


    def create_or_update_nics(
        self,
        device_id: int,
        nics_config: List[Dict],
    ) -> Tuple[bool, str, List[DeviceNicsPort]]:
        is_valid, error_msg = NicValidator.validate_nic_config(nics_config)
        if not is_valid:
            return (False, error_msg, [])

        device = self.repo.session.get(Device, device_id)
        if not device:
            return (False, f"设备不存在: {device_id}", [])

        occupied_count = self.repo.count_ports_by_device(
            device_id, filters={"port_status": "occupied"}
        )
        if occupied_count > 0:
            return (
                False,
                f"有 {occupied_count} 个端口正在使用中，请先删除相关连接后再修改网卡配置",
                [],
            )

        ports_data = NicValidator.prepare_ports_for_db(device_id, nics_config)
        try:
            with self.repo.session.begin_nested():
                count = self.repo.create_ports_batch(device_id, ports_data)
            new_ports = self.repo.find_ports_by_device_orm(device_id)
            logger.info("设备 %d 网卡配置保存成功，共 %d 个端口", device_id, count)
            return (True, f"网卡配置保存成功，共 {count} 个端口", new_ports)
        except Exception as e:
            logger.error("保存网卡配置失败: device_id=%d, error=%s", device_id, e)
            return (False, f"保存网卡配置失败: {e}", [])


    def batch_create_ports(
        self,
        device_id: int,
        ports_data: List[Dict],
    ) -> Tuple[bool, str, List[DeviceNicsPort]]:
        device = self.repo.session.get(Device, device_id)
        if not device:
            return (False, f"设备不存在: {device_id}", [])

        existing_ports = self.repo.find_ports_by_device_orm(device_id)
        existing_keys = {(p.nic_number, p.port_number) for p in existing_ports}
        new_keys: set = set()
        valid_speeds = NicValidator.VALID_PORT_SPEEDS
        valid_types = NicValidator.VALID_PORT_TYPES

        for i, p in enumerate(ports_data):
            nic_num = p.get('nic_number')
            port_num = p.get('port_number')
            if not nic_num or not port_num:
                return (False, f"第 {i + 1} 条：网卡号和端口号为必填", [])
            key = (nic_num, port_num)
            if key in existing_keys:
                return (False, f"第 {i + 1} 条：网卡{nic_num}端口{port_num}已存在", [])
            if key in new_keys:
                return (False, f"第 {i + 1} 条：网卡{nic_num}端口{port_num}与批次内其他条目重复", [])
            new_keys.add(key)
            port_type = p.get('port_type', '')
            port_speed = p.get('port_speed', '')
            if port_type and port_type not in valid_types:
                return (False, f"第 {i + 1} 条：非法端口类型 '{port_type}'", [])
            if port_speed and port_speed not in valid_speeds:
                return (False, f"第 {i + 1} 条：非法端口速率 '{port_speed}'", [])

        try:
            with self.repo.session.begin_nested():
                objs = [
                    DeviceNicsPort(
                        device_id=device_id,
                        nic_number=p.get('nic_number'),
                        nic_name=p.get('nic_name', ''),
                        port_number=p.get('port_number'),
                        port_name=p.get('port_name', ''),
                        port_type=p.get('port_type', 'RJ45'),
                        port_speed=p.get('port_speed', '1G'),
                        port_status=p.get('port_status', 'free'),
                        description=p.get('description', ''),
                    )
                    for p in ports_data
                ]
                self.repo.session.add_all(objs)
                self.repo.session.flush()

            logger.info("设备 %d 增量批量创建 %d 个端口", device_id, len(objs))
            all_ports = self.repo.find_ports_by_device_orm(device_id)
            return (True, f"成功创建 {len(objs)} 个端口", all_ports)
        except Exception as e:
            logger.error("增量批量创建端口失败: device_id=%d, error=%s", device_id, e)
            return (False, f"创建端口失败: {e}", [])

    def batch_create_for_devices(
        self,
        device_ids: List[int],
        ports_template: List[Dict],
    ) -> Dict:
        if not device_ids or not ports_template:
            return {"created": 0, "skipped": 0, "failed_devices": []}

        created = 0
        skipped = 0
        failed_devices: List[int] = []

        try:
            with self.repo.session.begin_nested():
                for device_id in device_ids:
                    device = self.repo.session.get(Device, device_id)
                    if not device:
                        skipped += 1
                        continue

                    existing_keys = set(
                        self.repo.session.query(
                            DeviceNicsPort.nic_number, DeviceNicsPort.port_number
                        )
                        .filter(DeviceNicsPort.device_id == device_id)
                        .all()
                    )

                    objs = []
                    for p in ports_template:
                        key = (p.get('nic_number'), p.get('port_number'))
                        if key in existing_keys:
                            continue
                        objs.append(DeviceNicsPort(
                            device_id=device_id,
                            nic_number=p.get('nic_number'),
                            port_number=p.get('port_number'),
                            port_name=p.get('port_name', ''),
                            port_type=p.get('port_type', 'RJ45'),
                            port_speed=p.get('port_speed', '1G'),
                            port_status='free',
                            description=p.get('description', ''),
                        ))
                    if objs:
                        self.repo.session.add_all(objs)
                        created += 1
                    else:
                        skipped += 1
                self.repo.session.flush()
        except Exception as e:
            logger.error("batch_create_for_devices 失败: error=%s", e)
            raise

        logger.info(
            "batch_create_for_devices: %d 台设备 × %d 端口，跳过 %d",
            created, len(ports_template), skipped,
        )
        return {"created": created, "skipped": skipped, "failed_devices": failed_devices}


    def get_device_ports(self, device_id: int) -> List[DeviceNicsPort]:
        return self.repo.find_ports_by_device_orm(device_id)

    def get_port_by_id(self, port_id: int) -> Optional[DeviceNicsPort]:
        return self.repo.find_port_by_id_orm(port_id)

    def get_port_by_nic_port(
        self, device_id: int, nic_number: int, port_number: int,
    ) -> Optional[DeviceNicsPort]:
        return self.repo.find_port_by_nic_port_orm(device_id, nic_number, port_number)

    def get_ports_by_type_speed(
        self, device_id: int, port_type: str = None, port_speed: str = None,
    ) -> List[DeviceNicsPort]:
        return self.repo.find_ports_by_type_speed_orm(device_id, port_type, port_speed)


    def update_port_status(self, port_id: int, status: str) -> Tuple[bool, str]:
        valid_statuses = {"free", "occupied", "disabled", "error"}
        if status not in valid_statuses:
            return (False, f"非法状态值: {status}")
        ok = self.repo.update_port_status(port_id, status)
        if not ok:
            return (False, f"端口不存在: {port_id}")
        return (True, f"端口状态更新为: {status}")

    def delete_device_ports(self, device_id: int) -> Tuple[bool, str]:
        occupied = self.repo.count_ports_by_device(
            device_id, filters={"port_status": "occupied"}
        )
        if occupied > 0:
            return (False, f"有 {occupied} 个端口正在使用中，无法删除")
        try:
            deleted = self.repo.delete_device_ports(device_id)
            return (True, f"成功删除 {deleted} 个端口")
        except Exception as e:
            return (False, f"删除端口失败: {e}")

    def batch_delete_ports(self, device_id: int, port_ids: List[int]) -> Dict:
        if not port_ids:
            return {"deleted": [], "skipped": []}

        ports = self.repo.find_ports_by_ids(port_ids)
        deleted: List[int] = []
        skipped: List[Dict] = []

        try:
            for p in ports:
                if p.device_id != device_id:
                    skipped.append({"id": p.id, "reason": "不属于该设备"})
                    continue
                if p.port_status == "occupied":
                    skipped.append({"id": p.id, "reason": "端口占用中，请先删除连接"})
                    continue
                self.repo.session.delete(p)
                deleted.append(p.id)
            self.repo.session.flush()
        except Exception as e:
            logger.error("批量删除端口失败: device_id=%d, error=%s", device_id, e)
            return {"deleted": deleted, "skipped": skipped, "error": str(e)}

        return {"deleted": deleted, "skipped": skipped}


    def get_ports_summary(self, device_id: int) -> Dict:
        ports = self.get_device_ports(device_id)
        summary: Dict = {
            "total": len(ports), "available": 0, "occupied": 0,
            "disabled": 0, "error": 0,
            "by_type": {}, "by_speed": {}, "by_type_speed": {},
        }
        for port in ports:
            status = port.port_status
            if status == "free":   summary["available"] += 1
            elif status == "occupied": summary["occupied"] += 1
            elif status == "disabled": summary["disabled"] += 1
            elif status == "error":    summary["error"] += 1
            pt = port.port_type
            sp = port.port_speed
            summary["by_type"][pt] = summary["by_type"].get(pt, 0) + 1
            summary["by_speed"][sp] = summary["by_speed"].get(sp, 0) + 1
            ts = f"{pt}/{sp}"
            summary["by_type_speed"][ts] = summary["by_type_speed"].get(ts, 0) + 1
        return summary

    def get_child_device_ids(self, parent_device_id: int) -> list[int]:
        if self._device_repo is None:
            from app.persistence.device_repository import DeviceRepository
            self._device_repo = DeviceRepository()
        return self._device_repo.get_child_device_ids(parent_device_id)


device_nics_port_service = DeviceNicsPortService(repository=DeviceNicsPortRepository())
