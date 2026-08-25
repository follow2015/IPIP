# -*- coding: utf-8 -*-
"""
设备服务模块

所有设备业务逻辑由实例方法提供，通过 DeviceRepository 访问数据库，
不再使用静态方法直接执行裸 SQL。
"""
from app.utils.logging import get_logger
import re as _re
import ipaddress as _ipa
from typing import Any, Dict, List, Optional, Tuple

from app.models.device import Device
from app.core.enums import DeviceStatus
from app.persistence.device_repository import DeviceRepository
from app.utils.cache import cache_manager, cached
from app.exceptions.validation import ValidationError
from config import get_config
from app.services.switch_events import emit_resource_change_global

logger = get_logger(__name__)
config = get_config()


def _coerce_to_date(value: Any):
    """把任意日期输入归一化为 datetime.date，供 DeviceAsset 的 Date 列使用。

    前端 DatePicker(dayjs) 序列化可能产出：
    - dayjs 对象的 JSON：'2026-08-12T09:39:05.600Z'（ISO 8601 带毫秒+Z）
    - 'YYYY-MM-DD' 纯日期字符串
    - 已是 date/datetime 对象（直接用）
    - None / ''（清空，返回 None）

    MySQL DATE 列拒绝带时间成分的 ISO 字符串（errno 1292），
    此函数统一截断为 date。
    """
    if value is None or value == "":
        return None
    from datetime import date, datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            try:
                return datetime.fromisoformat(s[:10]).date()
            except ValueError:
                return None
    return value


def _parse_ip_address_json(ip_string: str):

    """解析 IP 字符串为 JSON 格式列表，支持多种输入格式：

    - 单个 IP: "192.168.1.2"
    - 逗号分隔: "192.168.1.2,192.168.1.3"
    - CIDR: "192.168.1.0/24"
    - 子网掩码: "192.168.1.0 255.255.255.0" → 存储为 "192.168.1.0/24"
    - 范围(简写): "192.168.1.4-10" → 存储为 "192.168.1.4-10"
    - 范围(完整): "192.168.1.4-192.168.1.10" → 存储为 "192.168.1.4-10"

    Args:
        ip_string: 逗号分隔的IP地址字符串

    Returns:
        IP地址JSON格式列表，如 [{"ip": "192.168.1.1", "is_primary": True}, ...]
    """
    if not ip_string:
        return None

    segments = [s.strip() for s in ip_string.split(",") if s.strip()]
    result_ips = []

    for seg in segments:
        cidr_m = _re.match(r"^(\d+\.\d+\.\d+\.\d+)/(\d+)$", seg)
        if cidr_m:
            try:
                _ipa.ip_network(seg, strict=False)
                result_ips.append(seg)
                continue
            except ValueError:
                pass

        mask_m = _re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)$", seg)
        if mask_m:
            net_str, mask_str = mask_m.group(1), mask_m.group(2)
            try:
                network = _ipa.ip_network(f"{net_str}/{mask_str}", strict=False)
                result_ips.append(str(network))
                continue
            except ValueError:
                pass

        range_m = _re.match(r"^(\d+\.\d+\.\d+\.\d+)-(.+)$", seg)
        if range_m:
            start_str, end_part = range_m.group(1), range_m.group(2)
            try:
                start_octets = list(map(int, start_str.split('.')))
                if _re.match(r"^\d+\.\d+\.\d+\.\d+$", end_part):
                    end_octets = list(map(int, end_part.split('.')))
                    if (start_octets[:3] == end_octets[:3]
                            and 0 <= end_octets[3] <= 255
                            and end_octets[3] >= start_octets[3]):
                        if start_octets[3] == end_octets[3]:
                            result_ips.append(start_str)
                        else:
                            result_ips.append(f"{start_str}-{end_octets[3]}")
                        continue
                else:
                    end_num = int(end_part)
                    if 0 <= end_num <= 255 and end_num >= start_octets[3]:
                        if start_octets[3] == end_num:
                            result_ips.append(start_str)
                        else:
                            result_ips.append(f"{start_str}-{end_num}")
                        continue
            except (ValueError, IndexError):
                pass

        result_ips.append(seg)

    if not result_ips:
        return None
    return [{"ip": ip, "is_primary": (i == 0)} for i, ip in enumerate(result_ips)]


def _format_capacity(capacity_gb: int) -> str:
    """将 GB 数值格式化为可读字符串（3840 GB → 3.75TB，1024 GB → 1TB）"""
    if capacity_gb >= 1024:
        tb = capacity_gb / 1024
        return f"{int(tb)}TB" if tb == int(tb) else f"{tb:.2f}TB".rstrip('0').rstrip('.')
    return f"{capacity_gb}GB"


class DeviceService:
    """设备服务类

    职责：设备的 CRUD、状态机管理、U 位冲突检测、机箱节点同步。
    数据访问：全部通过 DeviceRepository，不直接执行 SQL。
    """

    def __init__(self, device_repository: DeviceRepository):
        self.device_repository = device_repository
        self.cache_ttl = config.CACHE_TTL_DEVICE

    def _validate_brand(self, brand: Optional[str], device_type: Optional[str]) -> None:
        """校验 brand 必须命中 monitor_vendor_brands.enterprise_no（按 device_type 联合）。

        - brand 为空：放行（允许未指定厂商）
        - brand 非空：必须在 monitor_vendor_brands 中存在且 enabled=1
          若 device_type 也给定，则 (enterprise_no, device_type) 必须联合命中
        """
        if not brand:
            return
        from app.models.monitor_vendor_brand import MonitorVendorBrand
        q = self.session.query(MonitorVendorBrand).filter(
            MonitorVendorBrand.enterprise_no == str(brand),
            MonitorVendorBrand.enabled.is_(True),
        )
        if device_type:
            q = q.filter(MonitorVendorBrand.device_type == device_type)
        if q.first() is None:
            raise ValidationError(
                f"厂商标识 {brand!r} 不在厂商品牌库中"
                + (f"（device_type={device_type}）" if device_type else "")
                + "，请从下拉列表选择"
            )

    @property
    def session(self):
        """代理到 repository 的 session，避免直接引用 db.session"""
        return self.device_repository.session

    @staticmethod
    def _invalidate_cabinet_cache(cabinet_id: int) -> None:
        """失效机柜相关全部缓存（含 with_devices 和 layout 显式 key）。

        cabinet:{id}:* 无法匹配 cabinet:with_devices:{id} 和 cabinet:layout:{id}，
        因此必须显式失效这两个 key，否则 U 位布局图数据不会刷新。
        """
        cache_manager.invalidate_pattern(f"cabinet:{cabinet_id}:*")
        cache_manager.invalidate_pattern(f"cabinet:with_devices:{cabinet_id}")
        cache_manager.invalidate_pattern(f"cabinet:layout:{cabinet_id}")

    @staticmethod
    def _check_ip_consistency(device: Device) -> None:
        """开发模式下检查 switch_credentials.ip 与 management_ip 一致性。

        从 Device.to_dict 中提取，保持 to_dict 为纯序列化方法。
        """
        if device.device_type != "network" or not device.switch_credential:
            return
        sc = device.switch_credential
        if device.management_ip and sc.ip and device.management_ip != sc.ip:
            import os
            if os.getenv("FLASK_ENV") == "development":
                logger.warning(
                    "IP不一致: device_id=%d, switch_credentials.ip=%s, management_ip=%s",
                    device.id, sc.ip, device.management_ip,
                )


    VALID_DEVICE_TYPES = {
        'server': ['standalone', 'chassis', 'node', 'storage', 'gpu'],
        'network': ['switch', 'router', 'firewall'],
        'other': ['pdu', 'ups', 'other'],
    }

    @classmethod
    def validate_device_type(cls, device_type: str, device_subtype: str) -> Tuple[bool, Optional[str]]:
        """验证设备类型合法性

        Args:
            device_type: 主类型（server/network/other）
            device_subtype: 子类型

        Returns:
            tuple: (is_valid, error_message)
        """
        if device_type not in cls.VALID_DEVICE_TYPES:
            return False, f"设备主类型不合法，必须是: {', '.join(cls.VALID_DEVICE_TYPES.keys())}"

        if device_subtype not in cls.VALID_DEVICE_TYPES[device_type]:
            return False, f"设备子类型 '{device_subtype}' 与主类型 '{device_type}' 不匹配"

        return True, None


    def get_by_id(self, device_id: int) -> Optional[Device]:
        """根据 ID 获取设备对象"""
        return self.device_repository.find_by_id(device_id)

    def get_device_by_id(self, device_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取设备字典（API 层使用）"""
        device = self.device_repository.find_by_id(device_id)
        return device.to_dict() if device else None

    def get_by_device_name(self, device_name: str) -> Optional[Device]:
        """根据设备名称获取设备"""
        return self.device_repository.find_by_device_name(device_name)

    def get_by_serial_number(self, serial_number: str) -> Optional[Device]:
        """根据序列号获取设备"""
        return self.device_repository.find_by_serial_number(serial_number)


    def get_all_devices(
        self,
        cabinet_id: int = None,
        customer_id: int = None,
        device_id: int = None,
        room_id: int = None,
        parent_device_id: int = None,
        is_chassis: int = None,
        device_type: str = None,
        device_subtype: str = None,
        page: int = 1,
        page_size: int = 20,
        has_ssh: bool = None,
    ) -> Dict[str, Any]:
        """获取有效设备列表（分页）
        
        Args:
            cabinet_id: 按机柜ID过滤
            customer_id: 按客户ID过滤
            device_id: 按设备ID过滤
            room_id: 按机房ID过滤
            parent_device_id: 按父设备ID过滤（用于查询机箱节点）
            is_chassis: 按是否为机箱过滤（1=机箱，0=非机箱）
            device_type: 按设备主类型过滤（server/network/other）
            device_subtype: 按设备子类型过滤
            page: 页码
            page_size: 每页数量
            has_ssh: 按是否有SSH管理权限过滤（仅网络设备有效）
        """
        return self.device_repository.get_all_devices(
            cabinet_id=cabinet_id,
            customer_id=customer_id,
            device_id=device_id,
            room_id=room_id,
            parent_device_id=parent_device_id,
            is_chassis=is_chassis,
            device_type=device_type,
            device_subtype=device_subtype,
            page=page,
            page_size=page_size,
            has_ssh=has_ssh,
        )

    def search_devices(
        self,
        keyword: str = None,
        cabinet_id: int = None,
        device_type: str = None,
        status: int = None,
        customer_id: int = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """搜索设备（分页），结果自动转为字典"""
        result = self.device_repository.search_devices(
            keyword=keyword,
            device_type=device_type,
            status=status,
            cabinet_id=cabinet_id,
            customer_id=customer_id,
            page=page,
            page_size=page_size,
        )
        result["data"] = [d.to_dict() for d in result["data"]]
        return result

    def get_devices_by_cabinet(self, cabinet_id: int) -> List[Dict[str, Any]]:
        """获取机柜下所有设备"""
        return [d.to_dict() for d in self.device_repository.find_by_cabinet_id(cabinet_id)]

    def get_devices_by_customer(self, customer_id: int) -> List[Dict[str, Any]]:
        """获取客户的所有设备"""
        return [d.to_dict() for d in self.device_repository.find_by_customer_id(customer_id)]

    def get_devices_by_room(self, room_id: int) -> List[Dict[str, Any]]:
        """根据机房 ID 获取设备列表"""
        return [d.to_dict() for d in self.device_repository.find_by_room_id(room_id)]

    def get_chassis_nodes(self, chassis_id: int) -> List[Dict[str, Any]]:
        """获取机箱的节点列表（走 Repository）"""
        nodes = self.device_repository.find_nodes_by_chassis(chassis_id)
        return [n.to_dict() for n in nodes]


    def get_device_count(self) -> int:
        """获取有效设备总数"""
        return self.device_repository.count_active_devices()

    def get_device_count_by_cabinet(self, cabinet_id: int) -> int:
        """获取机柜内有效设备数量"""
        return self.device_repository.count_by_cabinet(cabinet_id)

    def get_device_count_by_room(self, room_id: int) -> int:
        """获取机房内有效设备数量"""
        return self.device_repository.count_by_room(room_id)

    @cached(key_pattern="device:statistics")
    def get_device_statistics(self) -> Dict[str, Any]:
        """获取设备统计信息（带缓存）"""
        return self.device_repository.get_device_statistics()


    def create_device(self, data: Dict[str, Any]) -> Device:
        """创建设备

        自动将硬件/资产字段路由到对应的 1:1 扩展表。
        使用嵌套事务保证主表和扩展表的原子性。

        当 data['auto_create_nodes'] 为 True 且设备为机箱时，
        在同一 savepoint 内原子生成全部子节点，避免前端两次 HTTP 请求的非原子问题。
        """
        auto_create_nodes: bool = data.pop("auto_create_nodes", False)
        node_hardware_fields: Dict = data.pop("node_hardware", {})
        storage_items: List[Dict] = data.pop("storage_items", [])
        nic_ports: List[Dict] = data.pop("nic_ports", [])

        dup = self.device_repository.check_device_name_duplicate(
            data.get("device_name", ""), data.get("cabinet_id")
        )
        if dup:
            raise ValidationError(f"同机柜内已存在同名设备: {data.get('device_name')}")

        self._validate_brand(data.get("brand"), data.get("device_type"))

        serial = data.get("serial_number")
        if serial and self.device_repository.check_serial_number_exists(serial):
            raise ValidationError(f"序列号已存在: {serial}")

        if data.get("cabinet_id") and data.get("u_position"):
            self._check_u_position(
                data["cabinet_id"], data["u_position"], data.get("height_u", 1)
            )

        if data.get("is_chassis") and data.get("node_rows") and data.get("node_cols"):
            data["total_nodes"] = data["node_rows"] * data["node_cols"]

        if data.get("parent_device_id"):
            parent = self.get_by_id(data["parent_device_id"])
            if parent:
                if parent.is_chassis and parent.node_rows and parent.node_cols:
                    capacity = parent.node_rows * parent.node_cols
                    existing_nodes = self.device_repository.find_nodes_by_chassis(parent.id)
                    if len(existing_nodes) >= capacity:
                        raise ValidationError(
                            f"机箱 {parent.device_name} 容量已满（{capacity} 个节点），无法继续添加子节点。"
                        )
                if data.get("node_row") and data.get("node_col") and parent.node_cols:
                    data["node_position"] = (data["node_row"] - 1) * parent.node_cols + data["node_col"]
                if not data.get("cabinet_id") and parent.cabinet_id:
                    data["cabinet_id"] = parent.cabinet_id

        ip_json = None
        ip_explicit_clear = False
        if "ip_address" in data:
            if isinstance(data.get("ip_address"), str) and data["ip_address"]:
                ip_json = _parse_ip_address_json(data["ip_address"])
            elif data.get("ip_address") is None or data.get("ip_address") == "":
                ip_explicit_clear = True

        main_data, hardware_fields, asset_fields = self._split_extension_fields(data)
        if ip_json is not None:
            hardware_fields["ip_address"] = ip_json
        elif ip_explicit_clear:
            hardware_fields["ip_address"] = None

        self._enrich_hardware_from_templates(hardware_fields)

        try:
            with self.session.begin_nested():
                from app.persistence.device_repository import DeviceRepository
                safe_data = {k: v for k, v in main_data.items() if k in DeviceRepository._WRITABLE_FIELDS}
                device = Device(**safe_data)
                self.session.add(device)
                self.session.flush()  # 获取 device.id，供后续 hardware/asset/nodes 使用

                is_chassis_auto = auto_create_nodes and device.is_chassis and device.node_rows and device.node_cols

                if hardware_fields and not is_chassis_auto:
                    from app.models.device_hardware import DeviceHardware
                    hw = DeviceHardware(device_id=device.id, **hardware_fields)
                    device.hardware = hw
                    self.session.add(hw)

                if asset_fields:
                    from app.models.device_asset import DeviceAsset
                    at = DeviceAsset(device_id=device.id, **asset_fields)
                    device.asset = at
                    self.session.add(at)

                if is_chassis_auto:
                    self._auto_create_chassis_nodes(device, node_hardware_fields, storage_items, nic_ports)

                if storage_items and not is_chassis_auto:
                    self._create_storage_items(device.id, storage_items)

                if nic_ports and not is_chassis_auto:
                    self._create_nic_ports(device.id, nic_ports)

                self.session.flush()

        except Exception:
            raise

        cache_manager.invalidate_pattern("device:*")
        if device.cabinet_id:
            self._update_cabinet_usage(device.cabinet_id)
            self._invalidate_cabinet_cache(device.cabinet_id)
        if device.customer_id:
            cache_manager.invalidate_pattern(f"customer:{device.customer_id}:*")

        self._check_ip_consistency(device)
        emit_resource_change_global("device", "create", ids=[device.id])
        logger.info("创建设备成功: device_id=%d, auto_nodes=%s", device.id, auto_create_nodes)
        return device

    def update_device(self, device_id: int, data: Dict[str, Any],
                      auto_create_nodes: bool = False,
                      node_hardware: Dict = None,
                      storage_items: List[Dict] = None,
                      nic_ports: List[Dict] = None,
                      overwrite_nodes: bool = False) -> Optional[Device]:
        """更新设备（BUG-7/8 修复版）

        自动将硬件/资产字段路由到对应的 1:1 扩展表。
        使用嵌套事务保证主表和扩展表的原子性。

        当 auto_create_nodes 为 True 且设备为机箱时，
        在同一 savepoint 内原子生成全部子节点。
        """
        device = self.get_by_id(device_id)
        if not device:
            return None

        new_name = data.get("device_name", device.device_name)
        new_cabinet = data.get("cabinet_id", device.cabinet_id)
        dup = self.device_repository.check_device_name_duplicate(
            new_name, new_cabinet, exclude_id=device_id
        )
        if dup:
            raise ValidationError(f"同机柜内已存在同名设备: {new_name}")

        self._validate_brand(
            data.get("brand", device.brand),
            data.get("device_type", device.device_type),
        )

        serial = data.get("serial_number")
        if serial and self.device_repository.check_serial_number_exists(serial, exclude_id=device_id):
            raise ValidationError(f"序列号已存在: {serial}")

        old_cabinet_id = device.cabinet_id
        old_customer_id = device.customer_id

        new_customer_id = data.get("customer_id", old_customer_id)
        if new_customer_id is not None and new_customer_id != old_customer_id:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(new_customer_id)

        if any(k in data for k in ("cabinet_id", "u_position", "height_u")):
            cabinet_id = data.get("cabinet_id", device.cabinet_id)
            u_position = data.get("u_position", device.u_position)
            height_u = data.get("height_u", device.height_u)
            if cabinet_id and u_position:
                self._check_u_position(cabinet_id, u_position, height_u, exclude_id=device_id)

        if "parent_device_id" in data or "node_position" in data:
            new_parent_id = data.get("parent_device_id", device.parent_device_id)
            new_position = data.get("node_position", device.node_position)
            if new_position in (None, "", "null"):
                new_position = None
            moved = (new_parent_id != device.parent_device_id)
            repos = (new_position != device.node_position)
            if new_parent_id is not None and (moved or repos):
                chassis = self.device_repository.find_chassis_by_id(new_parent_id)
                if not chassis:
                    raise ValidationError(f"所属机箱不存在 (ID: {new_parent_id})")
                if not chassis.is_chassis:
                    raise ValidationError(f"所属设备不是机箱类型 (ID: {new_parent_id})")
                if chassis.node_rows and chassis.node_cols:
                    capacity = chassis.node_rows * chassis.node_cols
                    existing = [
                        n for n in self.device_repository.find_nodes_by_chassis(new_parent_id)
                        if n.id != device_id
                    ]
                    if len(existing) >= capacity:
                        raise ValidationError(
                            f"机箱 {chassis.device_name} 容量已满（{capacity} 个节点），无法移入该节点。"
                        )
                if new_position is not None:
                    self.validate_node_position(
                        new_parent_id, new_position, exclude_device_id=device_id
                    )

        ip_json = None
        ip_explicit_clear = False
        if "ip_address" in data:
            if isinstance(data.get("ip_address"), str) and data["ip_address"]:
                ip_json = _parse_ip_address_json(data["ip_address"])
            elif data.get("ip_address") is None or data.get("ip_address") == "":
                ip_explicit_clear = True

        main_data, hardware_fields, asset_fields = self._split_extension_fields(data)
        if ip_json is not None:
            hardware_fields["ip_address"] = ip_json
        elif ip_explicit_clear:
            hardware_fields["ip_address"] = None

        self._enrich_hardware_from_templates(hardware_fields)

        if device.is_chassis:
            new_rows = main_data.get("node_rows", device.node_rows)
            new_cols = main_data.get("node_cols", device.node_cols)
            if (new_rows != device.node_rows or new_cols != device.node_cols) and not auto_create_nodes:
                new_capacity = (new_rows or 0) * (new_cols or 0)
                existing_nodes = self.device_repository.find_nodes_by_chassis(device_id)
                existing_count = len(existing_nodes)
                if existing_count > 0 and existing_count > new_capacity:
                    raise ValidationError(
                        f"机箱当前已归属 {existing_count} 个子节点，变更后容量为 "
                        f"{new_capacity}（{new_rows}×{new_cols}），无法容纳现有节点。"
                        f"请先移除多余节点，或在编辑时勾选「生成子节点」以重建"
                        f"（将清空原有节点及其 IP、连接等关联数据）。"
                    )

        try:
            with self.session.begin_nested():
                from app.persistence.device_repository import DeviceRepository
                for k, v in main_data.items():
                    if k in DeviceRepository._WRITABLE_FIELDS:
                        setattr(device, k, v)
                self.session.flush()

                is_chassis_auto = bool(auto_create_nodes and device.is_chassis and device.node_rows and device.node_cols)

                if hardware_fields and not is_chassis_auto:
                    from app.models.device_hardware import DeviceHardware
                    hw = device.hardware or DeviceHardware(device_id=device_id)
                    for k, v in hardware_fields.items():
                        setattr(hw, k, v)
                    if not device.hardware:
                        device.hardware = hw
                        self.session.add(hw)

                if asset_fields:
                    from app.models.device_asset import DeviceAsset
                    at = device.asset or DeviceAsset(device_id=device_id)
                    for k, v in asset_fields.items():
                        setattr(at, k, _coerce_to_date(v) if k in self._ASSET_DATE_FIELDS else v)
                    if not device.asset:
                        device.asset = at
                        self.session.add(at)

                if hardware_fields or asset_fields:
                    self.session.flush()

        except Exception:
            raise

        if device.is_chassis and device.node_rows and device.node_cols:
            device.total_nodes = device.node_rows * device.node_cols
            self.session.flush()
        elif not device.is_chassis:
            device.total_nodes = 0
            self.session.flush()

        if auto_create_nodes and device.is_chassis and device.node_rows and device.node_cols:
            try:
                with self.session.begin_nested():
                    self._auto_create_chassis_nodes(
                        device,
                        node_hardware or {},
                        storage_items or [],
                        nic_ports or [],
                        overwrite=overwrite_nodes,
                    )
            except Exception:
                raise

        if device.is_chassis:
            try:
                with self.session.begin_nested():
                    self.device_repository.sync_chassis_nodes(device_id, main_data)
            except Exception:
                raise

        cache_manager.invalidate_pattern(f"device:{device_id}:*")
        for cid in {old_cabinet_id, device.cabinet_id}:
            if cid:
                self._update_cabinet_usage(cid)
                self._invalidate_cabinet_cache(cid)
        for cust_id in {old_customer_id, device.customer_id}:
            if cust_id:
                cache_manager.invalidate_pattern(f"customer:{cust_id}:*")

        self._check_ip_consistency(device)
        emit_resource_change_global("device", "update", ids=[device_id])
        logger.info("更新设备成功: device_id=%d", device_id)
        return device

    def delete_device(self, device_id: int) -> bool:
        """删除设备（软删除主记录 + 硬删除关联数据）

        删除前将设备占用的 U 位/机柜/节点位置信息保存到
        device_hardware.device_config，删除后清空这些位置字段，
        确保机柜 U 位和机箱节点位置被正确释放。

        重要行为说明：
        - 设备主记录仅做软删除（设置 deleted_at），可通过 restore_device 恢复
        - 但关联数据（连接、网卡端口、存储、VLAN、LAG、网络端口、交换机凭据等）
          会被硬删除（物理 DELETE），因为 DB 的 FK ondelete="CASCADE" 仅在 DELETE
          时触发，软删除走 UPDATE 不会触发级联
        - restore_device 仅恢复设备的位置信息（从 device_config 快照），关联数据
          需从快照重建（网卡/存储已支持自动重建，连接/VLAN 等需手动重建）

        整个流程包裹在 begin_nested() (SAVEPOINT) 中，
        保证中间步骤失败时整体回滚，避免数据半清理状态。
        """
        from datetime import datetime, timezone

        device = self.get_by_id(device_id)
        if not device:
            return False

        cabinet_id = device.cabinet_id
        customer_id = device.customer_id

        try:
            with self.session.begin_nested():
                self._save_location_to_config(device)

                self._cleanup_device_dependencies(device_id)

                device.deleted_at = datetime.now(timezone.utc)

                self._clear_device_location_inline(device)

                self.session.flush()
        except Exception:
            raise

        cache_manager.invalidate_pattern(f"device:{device_id}:*")
        if cabinet_id:
            self._update_cabinet_usage(cabinet_id)
            self._invalidate_cabinet_cache(cabinet_id)
        if customer_id:
            cache_manager.invalidate_pattern(f"customer:{customer_id}:*")

        emit_resource_change_global("device", "delete", ids=[device_id])
        logger.info("删除设备成功: device_id=%d", device_id)
        return True

    def _cleanup_device_dependencies(self, device_id: int) -> None:
        """清理设备关联数据

        在删除设备前调用，按依赖顺序清理：
        1. 子节点（自引用 parent_device_id）
        2. 设备连接（device_id 侧 + switch_device_id 侧）
        3. 设备网卡端口
        4. 设备存储（硬盘）
        5. VLAN
        6. 链路聚合组
        7. 网络端口
        8. 交换机凭据及关联（status_cache, switch_port_ip）
        9. 交换机路由
        10. IP 封禁记录
        11. 配置备份及差异

        注意：虽然 DeviceConnection/DeviceNicsPort/DeviceStorage 的 FK 设了
        ondelete="CASCADE"，但主设备走软删除（UPDATE 而非 DELETE），DB CASCADE
        不会触发，因此必须在此显式清理。
        """
        from app.models.device_server_ext import DeviceServerExt
        from datetime import datetime as _dt, timezone as _tz

        session = self.session

        child_exts = session.query(DeviceServerExt).filter_by(parent_device_id=device_id).all()
        children = [ext.device for ext in child_exts if ext.device and ext.device.deleted_at is None]
        if children:
            self._save_children_location_to_chassis_config(device_id, children)
        for child in children:
            self._cleanup_device_dependencies(child.id)
            child.deleted_at = _dt.now(_tz.utc).replace(tzinfo=None)
            self._clear_device_location_inline(child)

        from app.persistence.device_connection_repository import DeviceConnectionRepository
        from app.persistence.device_nics_port_repository import DeviceNicsPortRepository
        from app.persistence.device_storage_repository import DeviceStorageRepository
        from app.persistence.vlan_repository import VLANRepository
        from app.persistence.link_aggregation_repository import LinkAggregationRepository
        from app.persistence.switch_port_repository import NetworkPortRepository
        from app.persistence.device_config_backup_repository import (
            DeviceConfigBackupRepository, DeviceConfigChangeRepository,
        )

        DeviceConnectionRepository(session).delete_device_connections(device_id)
        DeviceConnectionRepository(session).delete_switch_connections(device_id)
        DeviceNicsPortRepository(session).delete_device_ports(device_id)
        DeviceStorageRepository(session).delete_by_device(device_id)
        VLANRepository(session).delete_by_device_id(device_id)
        LinkAggregationRepository(session).delete_by_device_id(device_id)
        NetworkPortRepository(session).delete_device_ports(device_id)
        DeviceConfigChangeRepository(session).delete_by_device_id(device_id)
        DeviceConfigBackupRepository(session).delete_by_device_id(device_id)

        self._delete_switch_related(session, device_id)

        self._delete_monitor_related(session, device_id)

        session.flush()

    @staticmethod
    def _delete_switch_related(session, device_id: int) -> None:
        """清理无独立 Repository 的交换机关联数据

        这些模型（SwitchPortIP, IPSwitchInfo, SwitchStatusCache,
        SwitchCredentials, SwitchRoute, IPBanRecord）仅在设备删除时使用，
        建 Repository 属于过度工程。

        注意：DeviceHardware / DeviceServerExt 依赖 Device relationship 的
        cascade="all, delete-orphan" 自动清理，无需手动删除。
        """
        from app.models.switch_credentials import (
            SwitchCredentials, SwitchStatusCache, SwitchPortIP, IPSwitchInfo,
        )
        from app.models.switch_route import SwitchRoute
        from app.models.ip_model import IPBanRecord

        session.query(SwitchPortIP).filter_by(device_id=device_id).delete()
        session.query(IPSwitchInfo).filter_by(switch_id=device_id).delete()
        session.query(SwitchStatusCache).filter_by(device_id=device_id).delete()
        session.query(SwitchCredentials).filter_by(device_id=device_id).delete()
        session.query(SwitchRoute).filter_by(switch_id=device_id).delete()
        session.query(IPBanRecord).filter_by(switch_id=device_id).delete()

    @staticmethod
    def _delete_monitor_related(session, device_id: int) -> None:
        """清理设备监控相关数据（设备删除时级联）。

        清理目标：
        - DeviceMonitorStatus：监控状态行（reachable/last_checked_at 等）
        - DeviceMetricAlertState：指标告警态（温度/磁盘/端口/RAID/中断的 breached 标记）
        - MonitorAlertOutbox：告警发件箱（未投递的告警/恢复通知）
        - DeviceMonitorCredential：设备-凭据关联（多对多中间表）
        - DeviceMonitorTimeseriesHourly：时序聚合数据

        不清理 MonitorCredential 本身：凭据可被多设备共享，仅解除关联。
        时序原始表（device_monitor_probe_events）按设备分区/按时间过期，
        此处不清理（由独立 TTL 任务回收）。
        """
        from app.models.device_monitor_status import DeviceMonitorStatus
        from app.models.device_metric_alert_state import DeviceMetricAlertState
        from app.models.monitor_alert_outbox import MonitorAlertOutbox
        from app.models.monitor_credential import DeviceMonitorCredential
        from app.models.device_monitor_timeseries_hourly import DeviceMonitorTimeseriesHourly

        session.query(DeviceMonitorStatus).filter_by(device_id=device_id).delete()
        session.query(DeviceMetricAlertState).filter_by(device_id=device_id).delete()
        session.query(MonitorAlertOutbox).filter_by(device_id=device_id).delete()
        session.query(DeviceMonitorCredential).filter_by(device_id=device_id).delete()
        session.query(DeviceMonitorTimeseriesHourly).filter_by(device_id=device_id).delete()

    def change_device_status(self, device_id: int, new_status: int) -> Optional[Device]:
        """状态机转换"""
        device = self.get_by_id(device_id)
        if not device:
            return None

        if not DeviceStatus.can_transition(device.status, new_status):
            raise ValidationError(
                f"不允许从 '{DeviceStatus.STATUS_NAMES.get(device.status)}' "
                f"转换到 '{DeviceStatus.STATUS_NAMES.get(new_status)}'"
            )

        result = self.device_repository.update(device_id, {"status": new_status})
        emit_resource_change_global("device", "status_change", ids=[device_id])
        return result

    def update_device_location(self, device_id: int, cabinet_id: int) -> bool:
        """更新设备所在机柜"""
        device = self.get_by_id(device_id)
        if not device:
            raise ValidationError("设备不存在")

        old_cabinet_id = device.cabinet_id
        result = self.device_repository.update_location(device_id, cabinet_id)

        if result:

            device = self.get_by_id(device_id)
            if device and device.is_chassis and cabinet_id != old_cabinet_id:
                self.device_repository.sync_chassis_nodes(device_id, {"cabinet_id": cabinet_id})

            cache_manager.invalidate_pattern(f"device:{device_id}:*")
            if old_cabinet_id:
                self._update_cabinet_usage(old_cabinet_id)
                self._invalidate_cabinet_cache(old_cabinet_id)
            if cabinet_id and cabinet_id != old_cabinet_id:
                self._update_cabinet_usage(cabinet_id)
                self._invalidate_cabinet_cache(cabinet_id)

            emit_resource_change_global("device", "location_change", ids=[device_id])

        return result

    def batch_update_status(self, device_ids: List[int], new_status: int) -> int:
        """批量更新设备状态"""
        result = self.device_repository.batch_update_status(device_ids, new_status)
        emit_resource_change_global("device", "batch_update", ids=device_ids)
        return result

    def batch_update_hardware(
        self, device_ids: List[int], hardware_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """批量更新设备硬件配置

        替代前端串行 N 次 PATCH 请求的反模式。
        在单次请求中统一写入，全部成功或全部回滚。

        Args:
            device_ids: 目标设备 ID 列表（通常为同一机箱的所有节点）
            hardware_fields: 仅含硬件字段的字典（非硬件字段自动过滤）

        Returns:
            {'updated': int, 'skipped': int}
        """
        device_ids = [int(d) for d in device_ids]
        safe_hw = {k: v for k, v in hardware_fields.items() if k in self._HARDWARE_FIELDS}
        if not safe_hw:
            return {"updated": 0, "skipped": 0}

        self._enrich_hardware_from_templates(safe_hw)

        updated = 0
        skipped = 0

        try:
            with self.session.begin_nested():
                from app.models.device_hardware import DeviceHardware
                device_map = self.device_repository.find_by_ids(device_ids)
                for device_id in device_ids:
                    device = device_map.get(device_id)
                    if not device:
                        skipped += 1
                        continue
                    hw = device.hardware or DeviceHardware(device_id=device_id)
                    for k, v in safe_hw.items():
                        setattr(hw, k, v)
                    if not device.hardware:
                        device.hardware = hw
                        self.session.add(hw)
                    updated += 1
                self.session.flush()
        except Exception:
            raise

        cache_manager.invalidate_pattern("device:*")
        emit_resource_change_global("device", "batch_update", ids=device_ids)
        logger.info("批量更新硬件配置: updated=%d, skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}

    def batch_update_asset(
        self, device_ids: List[int], asset_fields: Dict[str, Any],
        auto_generate: bool = False,
    ) -> Dict[str, Any]:
        """批量更新设备资产信息

        Args:
            device_ids: 目标设备 ID 列表
            asset_fields: 仅含资产字段的字典
            auto_generate: 是否为每个设备自动生成资产编号

        Returns:
            {'updated': int, 'skipped': int}
        """
        device_ids = [int(d) for d in device_ids]
        safe_at = {k: v for k, v in asset_fields.items() if k in self._ASSET_FIELDS}
        if not safe_at and not auto_generate:
            return {"updated": 0, "skipped": 0}

        updated = 0
        skipped = 0

        try:
            with self.session.begin_nested():
                from app.models.device_asset import DeviceAsset
                device_map = self.device_repository.find_by_ids(device_ids)
                for device_id in device_ids:
                    device = device_map.get(device_id)
                    if not device:
                        skipped += 1
                        continue
                    at = device.asset or DeviceAsset(device_id=device_id)
                    for k, v in safe_at.items():
                        setattr(at, k, _coerce_to_date(v) if k in self._ASSET_DATE_FIELDS else v)
                    if auto_generate:
                        at.asset_number = self._generate_asset_number()
                    if not device.asset:
                        device.asset = at
                        self.session.add(at)
                    updated += 1
                self.session.flush()
        except Exception:
            raise

        cache_manager.invalidate_pattern("device:*")
        emit_resource_change_global("device", "batch_update", ids=device_ids)
        logger.info("批量更新资产信息: updated=%d, skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}

    def batch_update_metric_template_group(
        self, device_ids: List[int], metric_template_group_id: Optional[int]
    ) -> Dict[str, Any]:
        """批量设置/清除设备的显式指标模板组关联。

        用于「批量修改监控」弹窗：选中多台设备统一绑定（或清除）某个指标模板组。
        ``metric_template_group_id`` 传 None 表示清除（回到自动匹配）。

        安全约束：仅更新主表可写字段（metric_template_group_id 已在 _WRITABLE_FIELDS），
        不触碰其他字段；设备不存在或组不存在时跳过并计数。

        Args:
            device_ids: 目标设备 ID 列表
            metric_template_group_id: 目标模板组 ID（None = 清除关联）

        Returns:
            {'updated': int, 'skipped': int}
        """
        from app.persistence.device_repository import DeviceRepository
        from app.persistence.monitor_metric_template_group_repository import (
            MonitorMetricTemplateGroupRepository,
        )
        from app.persistence.monitor_credential_repository import (
            MonitorCredentialRepository,
        )

        if not device_ids:
            raise ValidationError("device_ids 不能为空")

        group = None
        if metric_template_group_id is not None:
            group = MonitorMetricTemplateGroupRepository().find_by_id(
                metric_template_group_id
            )
            if not group:
                raise ValidationError("指标模板组不存在")

        cred_repo = MonitorCredentialRepository()
        updated = 0
        skipped = 0
        for did in device_ids:
            device = self.device_repository.find_by_id(did)
            if not device:
                skipped += 1
                continue
            if group is not None:
                if group.device_type != device.device_type:
                    skipped += 1
                    continue
                if group.vendor and (device.brand or "") != group.vendor:
                    skipped += 1
                    continue
                enabled_protocols = cred_repo.find_enabled_protocols(did)
                if group.source not in enabled_protocols:
                    skipped += 1
                    continue
            device.metric_template_group_id = metric_template_group_id
            self.device_repository.session.flush()
            updated += 1

        emit_resource_change_global("device", "batch_update", ids=device_ids)
        logger.info(
            "批量更新指标模板组: updated=%d, skipped=%d, group_id=%s",
            updated, skipped, metric_template_group_id,
        )
        return {"updated": updated, "skipped": skipped}

    def batch_update_port_sync_enabled(
        self, device_ids: List[int], port_sync_enabled: Optional[bool]
    ) -> Dict[str, Any]:
        """批量设置/清除设备的端口同步开关。

        用于「批量修改监控」弹窗：选中多台设备统一开启/关闭/跟随全局端口同步。
        ``port_sync_enabled`` 传 None 表示跟随全局开关（清除设备级覆盖）。

        仅对网络设备（device_type='network'）生效；非网络设备跳过。
        DeviceSwitchExt 不存在时自动创建。

        返回值区分：
        - updated: 网络设备数（开关已写入）
        - with_credential: 其中有 SNMP/Zabbix 凭据的设备数（能立即同步）
        - without_credential: 其中无凭据的设备数（开关已设但需配置凭据后才生效）
        - non_network: 非网络设备数（跳过）
        - skipped: 兼容字段 = non_network + 不存在设备数

        Args:
            device_ids: 目标设备 ID 列表
            port_sync_enabled: True=强制开, False=强制关, None=跟随全局

        Returns:
            {updated, with_credential, without_credential, non_network, skipped}
        """
        from app.models.device_switch_ext import DeviceSwitchExt
        from app.persistence.monitor_credential_repository import (
            MonitorCredentialRepository,
        )

        if not device_ids:
            raise ValidationError("device_ids 不能为空")

        cred_repo = MonitorCredentialRepository()
        with_cred_ids = set(
            cred_repo.find_enabled_device_ids(protocols=["snmp", "zabbix"])
        )

        updated = 0
        non_network = 0
        not_found = 0
        with_credential = 0
        without_credential = 0
        for did in device_ids:
            device = self.device_repository.find_by_id(did)
            if not device:
                not_found += 1
                continue
            if device.device_type != "network":
                non_network += 1
                continue
            ext = (
                self.device_repository.session.query(DeviceSwitchExt)
                .filter_by(device_id=did)
                .first()
            )
            if ext is None:
                ext = DeviceSwitchExt(device_id=did)
                self.device_repository.session.add(ext)
            ext.port_sync_enabled = port_sync_enabled
            self.device_repository.session.flush()
            updated += 1
            if did in with_cred_ids:
                with_credential += 1
            else:
                without_credential += 1

        emit_resource_change_global("device", "batch_update", ids=device_ids)
        logger.info(
            "批量更新端口同步开关: updated=%d (with_credential=%d, without_credential=%d), "
            "non_network=%d, not_found=%d, port_sync_enabled=%s",
            updated, with_credential, without_credential,
            non_network, not_found, port_sync_enabled,
        )
        return {
            "updated": updated,
            "with_credential": with_credential,
            "without_credential": without_credential,
            "non_network": non_network,
            "skipped": non_network + not_found,
        }

    def batch_update_config(
        self, device_ids: List[int], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """批量修改设备配置（通用字段 + 硬件配置 / 网络拓扑 + 端口生成）

        用于设备列表的「批量修改配置」功能：选中同子类型的多台设备，
        一次性更新通用字段（品牌/型号/功耗/负责人/客户），并按设备类型
        更新硬件配置（服务器）或网络拓扑与端口（网络设备）。

        安全约束：
        - 通用字段白名单：brand/device_model/power/responsible_person/customer_id
        - 硬件字段经 _HARDWARE_FIELDS 白名单过滤，且强制排除 ipmi_address
          （批量场景不覆盖 IPMI 管理地址，避免误改；但允许 ipmi_username/password）
        - NIC 端口 / 交换机端口由前端展开为完整端口列表后传入，后端仅落库

        Args:
            device_ids: 目标设备 ID 列表（调用方须已校验子类型一致）
            payload: {
                'main': {通用字段},
                'hardware': {DeviceHardware 字段（不含 ipmi_address）},
                'nic_ports': [{nic_number,port_number,port_type,port_speed,nic_name,port_name,description}],
                'switch_config': {switch_role,layer,uplink_device_id,core_device_id,port_num},
                'switch_ports': [{port_name,port_type,speed,usage_status}],
            }

        Returns:
            {'updated','skipped','nic_created','port_created','storage_created'}
        """
        from app.models.device_hardware import DeviceHardware
        from app.models.device_switch_ext import DeviceSwitchExt
        from app.persistence.device_repository import DeviceRepository

        device_ids = [int(d) for d in device_ids]

        COMMON_FIELDS = frozenset(
            {"brand", "device_model", "power", "responsible_person", "customer_id"}
        )
        raw_main = payload.get("main") or {}
        main_safe = {
            k: v
            for k, v in raw_main.items()
            if k in COMMON_FIELDS
            and k in DeviceRepository._WRITABLE_FIELDS
            and v not in (None, "", [])
        }

        if "brand" in main_safe:
            self._validate_brand(main_safe["brand"], None)

        raw_hw = payload.get("hardware") or {}
        hw_safe = {
            k: v
            for k, v in raw_hw.items()
            if k in self._HARDWARE_FIELDS and k != "ipmi_address"
            and v not in (None, "", [])
        }
        if hw_safe:
            self._enrich_hardware_from_templates(hw_safe)

        raw_sc = payload.get("switch_config") or {}
        sc_device = {
            k: raw_sc[k]
            for k in ("switch_role", "layer")
            if k in raw_sc and raw_sc[k] not in (None, "")
        }
        sc_ext = {
            k: raw_sc[k]
            for k in ("uplink_device_id", "core_device_id", "port_num", "uplink_port_ids")
            if k in raw_sc and raw_sc[k] not in (None, "", [])
        }

        nic_ports = payload.get("nic_ports") or []
        switch_ports = payload.get("switch_ports") or []
        storage_items = payload.get("storage_items") or []

        has_work = bool(
            main_safe or hw_safe or sc_device or sc_ext
            or nic_ports or switch_ports or storage_items
        )
        if not has_work:
            return {
                "updated": 0,
                "skipped": 0,
                "nic_created": 0,
                "port_created": 0,
            }

        device_map = self.device_repository.find_by_ids(device_ids)

        updated = 0
        skipped = 0
        nic_created = 0
        port_created = 0
        storage_created = 0

        try:
            with self.session.begin_nested():
                for device_id in device_ids:
                    device = device_map.get(device_id)
                    if not device:
                        skipped += 1
                        continue

                    for k, v in main_safe.items():
                        setattr(device, k, v)

                    if hw_safe:
                        hw = device.hardware or DeviceHardware(device_id=device_id)
                        for k, v in hw_safe.items():
                            setattr(hw, k, v)
                        if not device.hardware:
                            device.hardware = hw
                            self.session.add(hw)

                    if sc_ext:
                        if device.switch_ext:
                            for k, v in sc_ext.items():
                                setattr(device.switch_ext, k, v)
                        else:
                            ext = DeviceSwitchExt(device_id=device.id, **sc_ext)
                            self.session.add(ext)
                            device.switch_ext = ext
                    if sc_device:
                        for k, v in sc_device.items():
                            setattr(device, k, v)

                    if nic_ports:
                        try:
                            from app.persistence.device_nics_port_repository import (
                                DeviceNicsPortRepository,
                            )

                            cnt = DeviceNicsPortRepository(
                                self.session
                            ).create_ports_batch(device_id, nic_ports)
                            nic_created += cnt
                        except Exception as e:  # 已存在连接等，跳过该设备端口创建
                            logger.warning(
                                "批量配置-网卡端口覆盖跳过 设备%d: %s", device_id, e
                            )

                    if storage_items:
                        try:
                            from app.persistence.device_storage_repository import (
                                DeviceStorageRepository,
                            )

                            DeviceStorageRepository(self.session).delete_by_device(device_id)
                            self._create_storage_items(device_id, storage_items)
                            storage_created += len(storage_items)
                        except Exception as e:
                            logger.warning(
                                "批量配置-存储创建跳过 设备%d: %s", device_id, e
                            )

                    if switch_ports:
                        try:
                            from app.services.network_port_service import (
                                NetworkPortService,
                            )
                            from app.persistence.switch_port_repository import (
                                NetworkPortRepository,
                            )

                            cnt = NetworkPortService(NetworkPortRepository()).create_ports_batch(
                                device_id, switch_ports
                            )
                            port_created += cnt
                        except Exception as e:
                            logger.warning(
                                "批量配置-交换机端口创建跳过 设备%d: %s", device_id, e
                            )

                    self.session.flush()
                    updated += 1
        except Exception:
            raise

        cache_manager.invalidate_pattern("device:*")
        emit_resource_change_global("device", "batch_update_config", ids=device_ids)
        logger.info(
            "批量修改配置: updated=%d, skipped=%d, nic=%d, ports=%d",
            updated,
            skipped,
            nic_created,
            port_created,
        )
        return {
            "updated": updated,
            "skipped": skipped,
            "nic_created": nic_created,
            "port_created": port_created,
            "storage_created": storage_created,
        }

    def batch_reset_asset(self, device_ids: List[int]) -> Dict[str, Any]:
        """批量重置（清空）设备资产信息

        Args:
            device_ids: 目标设备 ID 列表

        Returns:
            {'updated': int, 'skipped': int}
        """
        updated = 0
        skipped = 0

        try:
            with self.session.begin_nested():
                for device_id in device_ids:
                    device = self.device_repository.find_by_id(device_id)
                    if not device:
                        skipped += 1
                        continue
                    if device.asset:
                        device.asset.asset_number = None
                        device.asset.supplier = None
                        device.asset.supplier_contact = None
                        device.asset.contract_number = None
                        device.asset.purchase_date = None
                        device.asset.purchase_price = None
                        device.asset.invoice_number = None
                        device.asset.warranty_start = None
                        device.asset.warranty_end = None
                        device.asset.warranty_type = None
                        device.asset.online_date = None
                        device.asset.offline_date = None
                        device.asset.lifecycle_years = None
                    updated += 1
                self.session.flush()
        except Exception:
            raise

        cache_manager.invalidate_pattern("device:*")
        emit_resource_change_global("device", "batch_update", ids=device_ids)
        logger.info("批量重置资产信息: updated=%d, skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}

    @staticmethod
    def _generate_asset_number(prefix: str = "ZC") -> str:
        """生成资产编号：ZC-YYYYMMDD-HHmmss-XXXX"""
        from datetime import datetime, timezone
        import random
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y%m%d")
        time_part = now.strftime("%H%M%S")
        rand_part = str(random.randint(0, 9999)).zfill(4)
        return f"{prefix}-{date_part}-{time_part}-{rand_part}"


    def generate_serial_number(
        self,
        prefix: str = "SN",
        format_type: str = "timestamp",
        length: int = 16,
    ) -> str:
        """生成唯一序列号（委托 Repository 实现，无 sleep 阻塞）"""
        return self.device_repository.generate_unique_serial_number(
            prefix=prefix, format_type=format_type, length=length
        )

    def is_serial_number_unique(self, serial_number: str, exclude_id: int = None) -> bool:
        """检查序列号是否唯一"""
        return not self.device_repository.check_serial_number_exists(
            serial_number, exclude_id=exclude_id
        )


    def validate_node_position(
        self,
        parent_device_id: int,
        node_position: int,
        exclude_device_id: int = None,
    ) -> Dict[str, Any]:
        """验证节点位置是否合法（走 Repository）

        检查项：所属机箱存在性、机箱类型、节点位置唯一性、节点数量上限。
        """
        chassis = self.device_repository.find_chassis_by_id(parent_device_id)
        if not chassis:
            raise ValidationError(f"所属机箱不存在 (ID: {parent_device_id})")
        if not chassis.is_chassis:
            raise ValidationError(f"所属设备不是机箱类型 (ID: {parent_device_id})")

        conflict = self.device_repository.find_node_by_position(
            parent_device_id, node_position, exclude_id=exclude_device_id
        )
        if conflict:
            raise ValidationError(
                f"节点位置 {node_position} 已被占用，设备: {conflict.device_name}"
            )

        if chassis.total_nodes and node_position > chassis.total_nodes:
            raise ValidationError(
                f"节点位置 {node_position} 超过机箱总节点数 {chassis.total_nodes}"
            )

        return chassis.to_dict()

    def check_node_position(
        self,
        chassis_id: int,
        node_position: int,
        exclude_device_id: int = None,
    ) -> Dict[str, Any]:
        """检查节点位置是否重复（走 Repository，API 层使用，不抛异常）"""
        conflict = self.device_repository.find_node_by_position(
            chassis_id, node_position, exclude_id=exclude_device_id
        )
        return {
            "is_duplicate": conflict is not None,
            "conflict_device": conflict.to_dict() if conflict else None,
        }

    def swap_node_positions(
        self,
        chassis_id: int,
        source_position: int,
        target_position: int,
    ) -> Dict[str, Any]:
        """交换/移动机箱节点位置（原子操作，供前端布局图拖拽调用）。

        语义（与前端拖拽一致，已与产品确认）：
        - source 必须是有节点的格子；target 可空可占用。
        - target 占用 → 两节点交换 node_position 与重算的 node_row/node_col。
        - target 空   → source 节点移动到 target。
        - 对符合「^.+-Node\\d+$」自动命名规则的节点，跟随新位置重命名；
          手动改过名的节点保持原名（与 sync_chassis_nodes 命名规则一致）。
        """
        chassis = self.get_by_id(chassis_id)
        if not chassis or not chassis.is_chassis:
            raise ValidationError("指定设备不是机箱或不存在")
        cols = chassis.node_cols
        rows = chassis.node_rows
        if not cols or not rows:
            raise ValidationError("机箱未配置节点行/列数")

        capacity = rows * cols
        for pos in (source_position, target_position):
            if pos < 1 or pos > capacity:
                raise ValidationError(f"节点位置 {pos} 超出机箱容量 {capacity}")
        if source_position == target_position:
            return {"swapped": False, "reason": "same_position"}

        source_node = self.device_repository.find_node_by_position(chassis_id, source_position)
        if not source_node:
            raise ValidationError(f"位置 {source_position} 没有节点，无法拖拽")

        target_node = self.device_repository.find_node_by_position(chassis_id, target_position)

        def _row_col(pos: int) -> Tuple[int, int]:
            return ((pos - 1) // cols) + 1, ((pos - 1) % cols) + 1

        def _rename_if_auto(name: Optional[str], new_pos: int) -> Optional[str]:
            if name and _re.match(r"^.+-Node\d+$", name):
                return _re.sub(r"-Node\d+$", f"-Node{new_pos}", name)
            return name

        with self.session.begin_nested():
            s_row, s_col = _row_col(target_position)
            source_node.server_ext.node_position = target_position
            source_node.server_ext.node_row = s_row
            source_node.server_ext.node_col = s_col
            new_name = _rename_if_auto(source_node.device_name, target_position)
            if new_name != source_node.device_name:
                source_node.device_name = new_name

            if target_node:
                t_row, t_col = _row_col(source_position)
                target_node.server_ext.node_position = source_position
                target_node.server_ext.node_row = t_row
                target_node.server_ext.node_col = t_col
                t_name = _rename_if_auto(target_node.device_name, source_position)
                if t_name != target_node.device_name:
                    target_node.device_name = t_name
            self.session.flush()

        return {
            "swapped": True,
            "source": source_position,
            "target": target_position,
            "exchanged": target_node is not None,
        }


    _HARDWARE_FIELDS = frozenset({
        "cpu", "cpu_way", "cpu_cores",
        "cpu_template_id",
        "memory", "memory_size_gb", "memory_dimm_count",
        "memory_template_id",
        "gpu", "gpu_count", "gpu_template_id",
        "storage_summary", "os_version",
        "ipmi_address", "ipmi_username", "ipmi_password", "device_config",
    })

    _FIELD_ALIAS = {
        "storage": "storage_summary",
    }

    _ASSET_FIELDS = frozenset({
        "asset_number", "supplier", "supplier_contact", "contract_number",
        "purchase_date", "purchase_price", "invoice_number",
        "warranty_start", "warranty_end", "warranty_type",
        "online_date", "offline_date", "lifecycle_years",
    })

    _ASSET_DATE_FIELDS = frozenset({
        "purchase_date", "warranty_start", "warranty_end",
        "online_date", "offline_date",
    })

    def _split_extension_fields(self, data: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """BUG-8 修复：不原地修改 data，返回三份独立字典

        同时处理字段别名映射：前端用 storage，数据库列为 storage_summary。

        Args:
            data: 原始数据字典

        Returns:
            (main_fields, hardware_fields, asset_fields)
        """
        mapped = {}
        for k, v in data.items():
            real_key = self._FIELD_ALIAS.get(k, k)
            mapped[real_key] = v

        hw = {k: v for k, v in mapped.items() if k in self._HARDWARE_FIELDS}
        at = {k: v for k, v in mapped.items() if k in self._ASSET_FIELDS}
        main = {k: v for k, v in mapped.items()
                if k not in self._HARDWARE_FIELDS and k not in self._ASSET_FIELDS}
        return main, hw, at

    def _resolve_component_template(self, template_id: int, category: str) -> dict:
        """加载配件模板并校验类别。

        Args:
            template_id: component_templates.id
            category:    预期类别 (cpu/memory/disk/nic/gpu)

        Returns:
            模板字典（含 spec）

        Raises:
            ValidationError: 模板不存在 或 类别与预期不符
        """
        from app.models.component_template import ComponentTemplate
        tpl = self.session.get(ComponentTemplate, template_id)
        if not tpl:
            raise ValidationError(f"配件模板 ID {template_id} 不存在")
        if tpl.category != category:
            raise ValidationError(
                f"模板 {template_id} 类别为 '{tpl.category}'，期望 '{category}'"
            )
        if not tpl.is_active:
            raise ValidationError(f"配件模板 {tpl.brand} {tpl.model} 已停用，无法使用")
        return tpl.to_dict()

    def _enrich_hardware_from_templates(self, hw_fields: dict) -> None:
        """根据模板 ID 自动填充 cpu / memory / gpu 文本字段（原地修改 hw_fields）。

        策略：setdefault 语义——用户显式传入的值优先于模板值。
        """
        cpu_tpl_id = hw_fields.get("cpu_template_id")
        if cpu_tpl_id:
            tpl = self._resolve_component_template(cpu_tpl_id, "cpu")
            spec = tpl.get("spec") or {}
            hw_fields.setdefault("cpu", f"{tpl['brand']} {tpl['model']}")
            hw_fields.setdefault("cpu_way", spec.get("way"))
            hw_fields.setdefault("cpu_cores", spec.get("cores_per_cpu"))

        dimm_count = hw_fields.get("memory_dimm_count") or 1

        mem_tpl_id = hw_fields.get("memory_template_id")
        if mem_tpl_id:
            tpl = self._resolve_component_template(mem_tpl_id, "memory")
            spec  = tpl.get("spec") or {}
            dimm  = dimm_count
            total = (spec.get("capacity_gb") or 0) * dimm
            mem_text = f"{tpl['brand']} {tpl['model']}"
            if tpl.get("remark"):
                mem_text += f" {tpl['remark']}"
            hw_fields["memory"] = mem_text
            if total:
                hw_fields.setdefault("memory_size_gb", total)

        if "memory_dimm_count" in hw_fields:
            hw_fields["memory_dimm_count"] = dimm_count

        gpu_tpl_id = hw_fields.get("gpu_template_id")
        if gpu_tpl_id:
            tpl = self._resolve_component_template(gpu_tpl_id, "gpu")
            gpu_count = hw_fields.get("gpu_count") or 1
            hw_fields["gpu"] = f"{tpl['brand']} {tpl['model']}"
            if "gpu_count" in hw_fields:
                hw_fields["gpu_count"] = gpu_count

    def _auto_create_chassis_nodes(self, chassis: Device, hardware_fields: Dict = None,
                                    storage_items: List[Dict] = None, nic_ports: List[Dict] = None,
                                    overwrite: bool = False) -> None:
        """在当前 savepoint 内原子生成机箱的全部子节点。

        调用方须在 begin_nested() 块内调用本方法，本方法不再嵌套事务。
        直接用 session.add() 而非 repository.create()，避免内部 commit 破坏 savepoint。
        节点命名规则：{chassis.device_name}-Node{pos}，可由 node_naming_pattern 覆盖。

        Args:
            chassis: 机箱设备对象
            hardware_fields: 子节点统一硬件配置（如 cpu, memory 等），写入 device_hardware 扩展表
            storage_items: 子节点统一存储配置，写入 device_storage 表
            nic_ports: 子节点统一网卡端口配置，写入 device_nics_port 表
            overwrite: 覆盖模式，True 时先删除所有旧子节点再重新生成
        """
        n_rows: int = chassis.node_rows
        n_cols: int = chassis.node_cols
        pattern: str = chassis.node_naming_pattern or "{chassis}-Node{pos}"
        hw_fields = hardware_fields or {}
        st_items = storage_items or []
        np_items = nic_ports or []

        from app.models.device_server_ext import DeviceServerExt

        if overwrite:
            old_nodes = self.device_repository.find_child_devices(chassis.id)
            for old_node in old_nodes:
                from app.models.device_hardware import DeviceHardware
                from app.models.device_server_ext import DeviceServerExt
                from app.persistence.device_nics_port_repository import DeviceNicsPortRepository
                from app.persistence.device_storage_repository import DeviceStorageRepository
                DeviceNicsPortRepository(self.session).delete_device_ports(old_node.id)
                DeviceStorageRepository(self.session).delete_by_device(old_node.id)
                self.session.query(DeviceHardware).filter_by(device_id=old_node.id).delete()
                self.session.query(DeviceServerExt).filter_by(device_id=old_node.id).delete()
                self.session.delete(old_node)
            self.session.flush()
            existing_positions = set()
        else:
            existing_positions = set(
                ext.node_position
                for ext in self.session.query(DeviceServerExt).filter_by(parent_device_id=chassis.id).all()
                if ext.node_position
            )

        if hw_fields:
            hw_fields = dict(hw_fields)  # 避免原地修改调用方的数据
            self._enrich_hardware_from_templates(hw_fields)

        created_count = 0
        for r in range(1, n_rows + 1):
            for c in range(1, n_cols + 1):
                pos = (r - 1) * n_cols + c
                if pos in existing_positions:
                    continue
                node_name = pattern.format(chassis=chassis.device_name, pos=pos, row=r, col=c)
                node = Device(
                    device_name=node_name,
                    device_type="server",
                    device_subtype="node",
                    parent_device_id=chassis.id,
                    node_position=pos,
                    node_row=r,
                    node_col=c,
                    cabinet_id=chassis.cabinet_id,
                    status=chassis.status,
                )
                self.session.add(node)
                self.session.flush()  # 获取 node.id

                if hw_fields:
                    from app.models.device_hardware import DeviceHardware
                    safe_hw = {k: v for k, v in hw_fields.items() if k in self._HARDWARE_FIELDS and v is not None}
                    if safe_hw:
                        hw = DeviceHardware(device_id=node.id, **safe_hw)
                        self.session.add(hw)

                if st_items:
                    self._create_storage_items(node.id, st_items)

                if np_items:
                    self._create_nic_ports(node.id, np_items)

                created_count += 1

        logger.info(
            "机箱 %d 自动生成 %d 个子节点 (%d行×%d列，已有 %d 个跳过)",
            chassis.id, created_count, n_rows, n_cols, len(existing_positions),
        )

    def _create_storage_items(self, device_id: int, items: List[Dict]) -> None:
        """创建设备存储条目，支持从配件模板自动填充字段。"""
        from app.models.device_storage import DeviceStorage
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        global_slot = 1  # 全局槽位计数器，跨 storage_items 递增

        for item in items:
            template_id = item.get("template_id")
            storage_type   = item.get("storage_type", "")
            capacity       = item.get("capacity", "")
            interface_type = item.get("interface_type")
            capacity_gb    = item.get("capacity_gb")
            manufacturer   = item.get("manufacturer")
            model_name     = item.get("model")

            if template_id:
                tpl = self._resolve_component_template(template_id, "disk")
                spec = tpl.get("spec") or {}
                storage_type   = storage_type   or spec.get("storage_type", "")
                capacity_gb    = capacity_gb    or spec.get("capacity_gb")
                interface_type = interface_type or spec.get("interface_type")
                manufacturer   = manufacturer   or tpl.get("brand")
                model_name     = model_name     or tpl.get("model")
                if not capacity and capacity_gb:
                    capacity = _format_capacity(capacity_gb)

            if not storage_type or not capacity:
                continue

            count = item.get("count", 1) or 1
            for i in range(count):
                st = DeviceStorage(
                    device_id=device_id,
                    storage_type=storage_type,
                    capacity=capacity,
                    capacity_gb=capacity_gb,
                    interface_type=interface_type,
                    manufacturer=manufacturer,
                    model=model_name,
                    template_id=template_id,
                    slot_number=item.get("slot_number", global_slot),
                    status="normal",
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(st)
                global_slot += 1

    def _create_nic_ports(self, device_id: int, ports: List[Dict]) -> None:
        """创建网卡端口记录，支持从配件模板展开多端口。

        增量语义：跳过该设备已存在的 (nic_number, port_number) 记录，
        避免 uk_device_nic_port 唯一键冲突。
        """
        from app.models.device_nics_port import DeviceNicsPort
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        nic_num = 1

        existing_keys = set(
            self.session.query(DeviceNicsPort.nic_number, DeviceNicsPort.port_number)
            .filter(DeviceNicsPort.device_id == device_id)
            .all()
        )

        for item in ports:
            template_id = item.get("template_id")
            port_type   = item.get("port_type", "RJ45")
            port_speed  = item.get("port_speed", "1G")
            nic_number  = item.get("nic_number", nic_num)

            if template_id:
                tpl = self._resolve_component_template(template_id, "nic")
                spec       = tpl.get("spec") or {}
                port_type  = spec.get("port_type",  port_type)
                port_speed = spec.get("port_speed", port_speed)
                port_count = spec.get("port_count", 1)
                model      = tpl.get("model", "")
                form_factor = spec.get("form_factor", "")
                tpl_remark  = tpl.get("remark", "")
                combined_desc = " ".join(filter(None, [tpl_remark, form_factor]))

                for port_num in range(1, port_count + 1):
                    key = (nic_number, port_num)
                    if key in existing_keys:
                        continue
                    auto_nic_name = f"{model}:端口{port_num}" if model else f"网卡{nic_num}"
                    auto_port_name = f"port{port_num}"
                    port = DeviceNicsPort(
                        device_id=device_id,
                        nic_number=nic_number,
                        nic_name=item.get("nic_name") or auto_nic_name,
                        port_number=port_num,
                        port_name=item.get("port_name") or auto_port_name,
                        port_type=port_type,
                        port_speed=port_speed,
                        port_status=item.get("port_status", "free"),
                        description=item.get("description") or combined_desc,
                        template_id=template_id,
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(port)
                    existing_keys.add(key)
            else:
                port_num = item.get("port_number", 1)
                key = (nic_number, port_num)
                if key not in existing_keys:
                    port = DeviceNicsPort(
                        device_id=device_id,
                        nic_number=nic_number,
                        nic_name=item.get("nic_name", f"网卡{nic_num}"),
                        port_number=port_num,
                        port_name=item.get("port_name", ""),
                        port_type=port_type,
                        port_speed=port_speed,
                        port_status=item.get("port_status", "free"),
                        description=item.get("description", ""),
                        template_id=template_id,
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(port)
                    existing_keys.add(key)

            nic_num += 1

    def _check_u_position(
        self,
        cabinet_id: int,
        u_position: int,
        height_u: int,
        exclude_id: int = None,
    ) -> None:
        """检查 U 位冲突，有冲突抛 ValidationError"""
        conflicts = self.device_repository.check_u_position_conflict(
            cabinet_id, u_position, height_u, exclude_id=exclude_id
        )
        if conflicts:
            names = [d.device_name for d in conflicts]
            raise ValidationError(f"U 位冲突，与以下设备冲突: {', '.join(names)}")

    def _save_location_to_config(self, device: Device) -> None:
        """删除设备前，将占用的 U 位/机柜/节点位置/网卡/硬盘信息保存到 device_hardware.device_config。

        保存的信息包括：
        - deleted_location_snapshot: 机柜/U位/节点位置
        - deleted_nics_snapshot: 网卡型号及端口信息
        - deleted_storage_snapshot: 硬盘型号及容量信息

        这些信息在设备恢复或审计查询时可以使用。
        """
        from app.models.device_hardware import DeviceHardware
        from app.models.device_nics_port import DeviceNicsPort
        from app.models.device_storage import DeviceStorage

        location_snapshot = {
            "cabinet_id": device.cabinet_id,
            "u_position": device.u_position,
            "height_u": device.height_u,
            "original_status": device.status,
        }
        if device.cabinet:
            location_snapshot["cabinet_number"] = device.cabinet.cabinet_number
            location_snapshot["room_id"] = device.cabinet.room_id
        if device.server_ext:
            se = device.server_ext
            location_snapshot["parent_device_id"] = se.parent_device_id
            location_snapshot["node_position"] = se.node_position
            location_snapshot["node_row"] = se.node_row
            location_snapshot["node_col"] = se.node_col

        nics_ports = self.session.query(DeviceNicsPort).filter_by(device_id=device.id).all()
        nics_snapshot = []
        for np in nics_ports:
            nics_snapshot.append({
                "id": np.id,
                "nic_number": np.nic_number,
                "nic_name": np.nic_name,
                "port_number": np.port_number,
                "port_name": np.port_name,
                "port_type": np.port_type,
                "port_speed": np.port_speed,
                "port_status": np.port_status,
                "template_id": np.template_id,
            })

        storages = self.session.query(DeviceStorage).filter_by(device_id=device.id).all()
        storage_snapshot = []
        for st in storages:
            storage_snapshot.append({
                "id": st.id,
                "storage_type": st.storage_type,
                "model": st.model,
                "capacity": st.capacity,
                "capacity_gb": st.capacity_gb,
                "interface_type": st.interface_type,
                "manufacturer": st.manufacturer,
                "slot_number": st.slot_number,
                "template_id": st.template_id,
                "serial_number": st.serial_number,
            })

        hardware = device.hardware
        if not hardware:
            hardware = DeviceHardware(device_id=device.id)
            self.session.add(hardware)
            self.session.flush()
            device.hardware = hardware

        existing_config = hardware.device_config or {}
        existing_config["deleted_location_snapshot"] = location_snapshot
        if nics_snapshot:
            existing_config["deleted_nics_snapshot"] = nics_snapshot
        if storage_snapshot:
            existing_config["deleted_storage_snapshot"] = storage_snapshot
        hardware.device_config = existing_config

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(hardware, "device_config")
        self.session.flush()
        logger.info(
            f"保存设备快照到 device_config: device_id={device.id}, "
            f"cabinet_id={device.cabinet_id}, u_position={device.u_position}, "
            f"nics={len(nics_snapshot)}, storage={len(storage_snapshot)}"
        )

    def _save_children_location_to_chassis_config(
        self, chassis_id: int, children: list
    ) -> None:
        """物理删除子节点前，将子节点的完整信息保存到机箱的 device_hardware.device_config。

        子节点被物理删除后，其 device_hardware / nics / storage 也会被级联删除，
        因此将子节点的完整快照（位置 + 硬件 + NIC + 存储）保存到机箱的 device_config 中，
        便于后续恢复时完整重建子节点。

        Args:
            chassis_id: 机箱设备ID
            children: 即将被物理删除的子节点列表
        """
        from app.models.device import Device
        from app.models.device_hardware import DeviceHardware
        from app.models.device_nics_port import DeviceNicsPort
        from app.models.device_storage import DeviceStorage

        children_snapshot = []
        for child in children:
            hw = child.hardware
            snapshot = {
                "device_id":     child.id,
                "device_name":   child.device_name,
                "serial_number": child.serial_number,
                "management_ip": child.management_ip,
                "height_u":      child.height_u,
                "node_position": child.node_position if child.server_ext else None,
                "node_row":      child.node_row if child.server_ext else None,
                "node_col":      child.node_col if child.server_ext else None,
                "hardware": {
                    "cpu":            hw.cpu if hw else None,
                    "cpu_way":        hw.cpu_way if hw else None,
                    "cpu_cores":      hw.cpu_cores if hw else None,
                    "memory":         hw.memory if hw else None,
                    "memory_size_gb": hw.memory_size_gb if hw else None,
                    "os_version":     hw.os_version if hw else None,
                    "ipmi_address":   hw.ipmi_address if hw else None,
                } if hw else {},
                "nics": [
                    {
                        "nic_number": p.nic_number, "nic_name": p.nic_name,
                        "port_number": p.port_number, "port_name": p.port_name,
                        "port_type": p.port_type, "port_speed": p.port_speed,
                        "port_status": p.port_status, "template_id": p.template_id,
                        "description": p.description,
                    }
                    for p in self.session.query(DeviceNicsPort).filter_by(device_id=child.id).all()
                ],
                "storage": [
                    {
                        "storage_type": s.storage_type, "model": s.model,
                        "capacity": s.capacity, "capacity_gb": s.capacity_gb,
                        "interface_type": s.interface_type, "manufacturer": s.manufacturer,
                        "slot_number": s.slot_number, "template_id": s.template_id,
                        "serial_number": s.serial_number,
                    }
                    for s in self.session.query(DeviceStorage).filter_by(device_id=child.id).all()
                ],
            }
            children_snapshot.append(snapshot)

        chassis = self.session.get(Device, chassis_id)
        if not chassis:
            return

        hardware = chassis.hardware
        if not hardware:
            hardware = DeviceHardware(device_id=chassis_id)
            self.session.add(hardware)
            self.session.flush()
            chassis.hardware = hardware

        existing_config = hardware.device_config or {}
        existing_children = existing_config.get("deleted_children_snapshot", [])
        existing_children.extend(children_snapshot)
        existing_config["deleted_children_snapshot"] = existing_children
        hardware.device_config = existing_config

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(hardware, "device_config")
        self.session.flush()
        logger.info(
            f"保存 {len(children_snapshot)} 个子节点位置快照到机箱 device_config: "
            f"chassis_id={chassis_id}"
        )

    def _clear_device_location_inline(self, device: Device) -> None:
        """直接操作已加载的 device 对象清空位置字段（savepoint 内使用，避免重复查询）"""
        device.cabinet_id = None
        device.u_position = None
        if device.server_ext:
            device.server_ext.parent_device_id = None
            device.server_ext.node_position = None
            device.server_ext.node_row = None
            device.server_ext.node_col = None


    def get_deleted_devices(self, **kwargs) -> Dict[str, Any]:
        """查询已软删除的设备列表（回收站）"""
        return self.device_repository.get_deleted_devices(**kwargs)

    def restore_device(
        self, device_id: int, cabinet_id: int = None, u_position: int = None,
        _skip_cabinet_update: bool = False,
    ) -> Dict[str, Any]:
        """恢复已软删除的设备

        1. 读取 device_config 中的位置快照
        2. 确定目标机柜和U位：
           - 未选机柜 → 恢复到原位置（快照）
           - 选了机柜 + 填了U位 → 使用指定位置
           - 选了机柜 + 未填U位 → 自动分配U位
        3. 检查U位冲突（仅原位置恢复时检测）
        4. 恢复设备（清 deleted_at）
        5. 回填位置
        6. 清理 device_config 快照
        7. 若是机箱 → 从快照重建子节点
        8. 更新机柜使用情况

        Returns:
            {"restored": bool, "location_conflict": bool, "conflict_devices": list,
             "auto_assigned_u_position": Optional[int]}
        """
        from app.models.device_hardware import DeviceHardware
        from app.models.device_server_ext import DeviceServerExt

        session = self.session
        device = self.device_repository.find_by_id_including_deleted(device_id)
        if not device or device.deleted_at is None:
            raise ValidationError("设备不存在或未被删除")

        hardware = device.hardware
        snapshot = {}
        if hardware and hardware.device_config:
            snapshot = hardware.device_config.get("deleted_location_snapshot", {})

        height_u = snapshot.get("height_u") or device.height_u or 1
        auto_assigned_u_position = None

        snapshot_parent_id = snapshot.get("parent_device_id")
        is_child_node = (device.server_ext is not None) and (
            device.server_ext.parent_device_id is not None or snapshot_parent_id is not None
        )
        if is_child_node and cabinet_id is not None:
            raise ValidationError("子节点设备只能恢复到原机箱，不能指定其他机柜")

        if cabinet_id is not None:
            target_cabinet_id = cabinet_id
            if u_position is not None:
                target_u_position = u_position
            else:
                try:
                    from app.services.cabinet_service import cabinet_service
                    target_u_position = cabinet_service.auto_allocate_u_position(
                        cabinet_id, height_u
                    )
                except ImportError:
                    target_u_position = None
                if target_u_position is None:
                    raise ValidationError(f"机柜 {cabinet_id} 无可用U位，无法自动分配")
                auto_assigned_u_position = target_u_position
        else:
            target_cabinet_id = snapshot.get("cabinet_id")
            target_u_position = snapshot.get("u_position")

        location_conflict = False
        conflict_devices = []
        if cabinet_id is None and target_cabinet_id and target_u_position:
            from app.models.cabinet import Cabinet
            cabinet = session.query(Cabinet).filter(Cabinet.id == target_cabinet_id).first()
            if cabinet:
                conflict_result = cabinet.check_u_position_conflict(
                    target_u_position, height_u, exclude_device_id=device_id
                )
                if conflict_result["has_conflict"]:
                    location_conflict = True
                    conflict_devices = conflict_result["conflicting_devices"]

        if location_conflict:
            return {
                "restored": False,
                "location_conflict": True,
                "conflict_devices": conflict_devices,
                "original_cabinet_id": target_cabinet_id,
                "original_u_position": target_u_position,
            }

        if is_child_node:
            original_parent_id = snapshot.get("parent_device_id")
            original_node_position = snapshot.get("node_position")
            if not original_parent_id:
                raise ValidationError("子节点缺少原机箱信息，无法恢复")
            parent_device = self.device_repository.find_by_id_including_deleted(original_parent_id)
            if not parent_device:
                raise ValidationError(f"原机箱不存在 (ID: {original_parent_id})，无法恢复")
            if parent_device.deleted_at is not None:
                raise ValidationError(f"原机箱已被删除，请先恢复机箱后再恢复子节点")
            if not (parent_device.server_ext and parent_device.server_ext.is_chassis):
                raise ValidationError(f"原所属设备已不是机箱类型 (ID: {original_parent_id})")
            if parent_device.total_nodes and original_node_position is not None and original_node_position > parent_device.total_nodes:
                raise ValidationError(
                    f"节点位置 {original_node_position} 超出机箱当前容量 {parent_device.total_nodes}，"
                    f"机箱可能在删除后被缩小"
                )
            if original_node_position is not None:
                conflict_node = self.device_repository.find_node_by_position(
                    original_parent_id, original_node_position, exclude_id=device_id
                )
                if conflict_node:
                    location_conflict = True
                    conflict_devices = [{"id": conflict_node.id, "name": conflict_node.device_name}]

        if location_conflict:
            return {
                "restored": False,
                "location_conflict": True,
                "conflict_devices": conflict_devices,
                "original_cabinet_id": target_cabinet_id,
                "original_u_position": target_u_position,
            }

        restored_children = []
        try:
            with self.session.begin_nested():
                device.deleted_at = None
                original_status = snapshot.get("original_status", DeviceStatus.AVAILABLE)
                safe_statuses = {DeviceStatus.AVAILABLE, DeviceStatus.ONLINE, DeviceStatus.OFFLINE, DeviceStatus.MAINTENANCE}
                device.status = original_status if original_status in safe_statuses else DeviceStatus.AVAILABLE

                if target_cabinet_id and target_u_position:
                    device.cabinet_id = target_cabinet_id
                    device.u_position = target_u_position
                elif target_cabinet_id and not target_u_position:
                    device.cabinet_id = target_cabinet_id

                if is_child_node and device.server_ext:
                    original_parent_id = snapshot.get("parent_device_id")
                    original_node_position = snapshot.get("node_position")
                    original_node_row = snapshot.get("node_row")
                    original_node_col = snapshot.get("node_col")
                    if original_parent_id:
                        device.server_ext.parent_device_id = original_parent_id
                    if original_node_position is not None:
                        device.server_ext.node_position = original_node_position
                    if original_node_row is not None:
                        device.server_ext.node_row = original_node_row
                    if original_node_col is not None:
                        device.server_ext.node_col = original_node_col

                if hardware and hardware.device_config:
                    from app.models.device_nics_port import DeviceNicsPort
                    from app.models.device_storage import DeviceStorage

                    nics_snap = hardware.device_config.get("deleted_nics_snapshot", [])
                    for ns in nics_snap:
                        existing = self.session.query(DeviceNicsPort).filter_by(
                            device_id=device_id, nic_number=ns.get("nic_number"),
                            port_number=ns.get("port_number")
                        ).first()
                        if not existing:
                            nic_port = DeviceNicsPort(
                                device_id=device_id,
                                nic_number=ns.get("nic_number"),
                                nic_name=ns.get("nic_name", ""),
                                port_number=ns.get("port_number"),
                                port_name=ns.get("port_name"),
                                port_type=ns.get("port_type", "RJ45"),
                                port_speed=ns.get("port_speed", "1G"),
                                port_status=ns.get("port_status", "free"),
                                template_id=ns.get("template_id"),
                            )
                            session.add(nic_port)

                    storage_snap = hardware.device_config.get("deleted_storage_snapshot", [])
                    for ss in storage_snap:
                        existing = None
                        if ss.get("serial_number"):
                            existing = self.session.query(DeviceStorage).filter_by(
                                serial_number=ss["serial_number"]
                            ).first()
                        if not existing:
                            storage = DeviceStorage(
                                device_id=device_id,
                                storage_type=ss.get("storage_type", "HDD"),
                                capacity=ss.get("capacity", ""),
                                capacity_gb=ss.get("capacity_gb"),
                                interface_type=ss.get("interface_type"),
                                slot_number=ss.get("slot_number"),
                                manufacturer=ss.get("manufacturer"),
                                model=ss.get("model"),
                                template_id=ss.get("template_id"),
                                serial_number=ss.get("serial_number"),
                            )
                            session.add(storage)

                is_chassis = device.server_ext and device.server_ext.is_chassis
                if is_chassis and hardware and hardware.device_config:
                    children_snapshot = hardware.device_config.get("deleted_children_snapshot", [])
                    if children_snapshot:
                        restored_children = self._restore_children_from_snapshot(
                            device, children_snapshot
                        )
                        remaining = [
                            s for s in children_snapshot
                            if s.get("device_id") not in [c.id for c in restored_children]
                        ]
                        config = hardware.device_config or {}
                        if remaining:
                            config["deleted_children_snapshot"] = remaining
                        else:
                            config.pop("deleted_children_snapshot", None)
                        hardware.device_config = config
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(hardware, "device_config")

                self._cleanup_device_config_snapshots(device)

                session.flush()
        except Exception:
            raise

        if not _skip_cabinet_update and device.cabinet_id:
            self._update_cabinet_usage(device.cabinet_id)
            self._invalidate_cabinet_cache(device.cabinet_id)

        cache_manager.invalidate_pattern(f"device:{device_id}:*")
        cache_manager.invalidate_pattern("devices:*")

        emit_resource_change_global("device", "create", ids=[device_id])

        logger.info(
            f"恢复设备成功: device_id={device_id}, "
            f"cabinet_id={device.cabinet_id}, u_position={device.u_position}, "
            f"auto_assigned={auto_assigned_u_position is not None}, "
            f"children_restored={len(restored_children)}"
        )
        return {
            "restored": True,
            "location_conflict": location_conflict,
            "conflict_devices": conflict_devices,
            "children_restored": len(restored_children),
            "auto_assigned_u_position": auto_assigned_u_position,
        }

    def permanent_delete_device(self, device_id: int) -> bool:
        """永久删除设备（物理 DELETE，不可恢复）

        只能删除已软删除的设备。
        """
        from app.models.device import Device

        session = self.session
        device = session.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise ValidationError("设备不存在")
        if device.deleted_at is None:
            raise ValidationError("设备未被软删除，不能直接永久删除")

        try:
            with self.session.begin_nested():
                self._cleanup_device_dependencies(device_id)

                session.delete(device)
                session.flush()
        except Exception:
            raise

        cache_manager.invalidate_pattern(f"device:{device_id}:*")
        cache_manager.invalidate_pattern("devices:*")
        emit_resource_change_global("device", "delete", ids=[device_id])
        logger.info("永久删除设备: device_id=%d", device_id)
        return True

    def batch_restore_devices(
        self, device_ids: List[int], cabinet_id: int = None, u_position: int = None
    ) -> Dict[str, Any]:
        """批量恢复设备

        位置确定逻辑：
        - 未选机柜 → 每个设备恢复到原位置（快照）
        - 选了机柜 + 填了U位 → 第一个设备使用指定U位，后续按 height_u 递增
        - 选了机柜 + 未填U位 → 第一个设备自动分配U位，后续按 height_u 递增
        批量完成后统一刷新受影响机柜的使用情况，避免 N+1 写。
        """
        from app.models.device import Device

        results = {"success": [], "failed": [], "conflict": []}
        affected_cabinet_ids: set = set()
        next_u_position = u_position  # 跟踪下一个可用U位
        first_device = True  # 标记是否为第一个设备（用于自动分配起始U位）

        for did in device_ids:
            try:
                dev = self.device_repository.find_by_id_including_deleted(did)
                snapshot_parent = None
                if dev and dev.hardware and dev.hardware.device_config:
                    snapshot_parent = dev.hardware.device_config.get(
                        "deleted_location_snapshot", {}
                    ).get("parent_device_id")
                is_child = (dev and dev.server_ext and dev.server_ext.parent_device_id is not None) or snapshot_parent is not None
                effective_cabinet_id = None if is_child else cabinet_id

                current_u_position = next_u_position
                if effective_cabinet_id is not None and u_position is None and not first_device:
                    current_u_position = next_u_position

                result = self.restore_device(
                    did,
                    cabinet_id=effective_cabinet_id,
                    u_position=current_u_position,
                    _skip_cabinet_update=True,  # 批量模式下跳过单次机柜刷新
                )
                if result.get("restored"):
                    results["success"].append(did)
                    restored_dev = self.session.get(Device, did)
                    if restored_dev:
                        if restored_dev.cabinet_id:
                            affected_cabinet_ids.add(restored_dev.cabinet_id)
                        if effective_cabinet_id is not None and restored_dev.height_u:
                            if restored_dev.u_position:
                                next_u_position = restored_dev.u_position + restored_dev.height_u
                                if effective_cabinet_id and next_u_position:
                                    conflicts = self.device_repository.check_u_position_conflict(
                                        effective_cabinet_id, next_u_position, restored_dev.height_u or 1
                                    )
                                    if conflicts:
                                        next_u_position = None
                    first_device = False
                else:
                    results["conflict"].append({"device_id": did, **result})
            except Exception as e:
                results["failed"].append({"device_id": did, "error": str(e)})

        for cid in affected_cabinet_ids:
            self._update_cabinet_usage(cid)
            self._invalidate_cabinet_cache(cid)

        if results["success"]:
            emit_resource_change_global("device", "batch_create", ids=results["success"])

        return results

    def batch_permanent_delete_devices(self, device_ids: List[int]) -> Dict[str, Any]:
        """批量永久删除设备（单次事务，全部成功或全部回滚）"""
        from app.models.device import Device

        session = self.session
        results = {"success": [], "failed": []}

        try:
            with self.session.begin_nested():
                for did in device_ids:
                    device = session.query(Device).filter(Device.id == did).first()
                    if not device:
                        results["failed"].append({"device_id": did, "error": "设备不存在"})
                        continue
                    if device.deleted_at is None:
                        results["failed"].append({"device_id": did, "error": "设备未被软删除"})
                        continue
                    self._cleanup_device_dependencies(did)
                    session.delete(device)
                    results["success"].append(did)
                session.flush()
        except Exception as e:
            results["failed"] = [{"device_id": did, "error": str(e)} for did in device_ids]
            results["success"] = []
            return results

        for did in results["success"]:
            cache_manager.invalidate_pattern(f"device:{did}:*")
        cache_manager.invalidate_pattern("devices:*")
        if results["success"]:
            emit_resource_change_global("device", "batch_delete", ids=results["success"])
        logger.info("批量永久删除设备: %d 台", len(results['success']))
        return results

    def _cleanup_device_config_snapshots(self, device: Device) -> None:
        """恢复设备后，清理 device_config 中的删除快照"""
        from sqlalchemy.orm.attributes import flag_modified

        hardware = device.hardware
        if not hardware or not hardware.device_config:
            return

        config = dict(hardware.device_config)
        config.pop("deleted_location_snapshot", None)
        config.pop("deleted_nics_snapshot", None)
        config.pop("deleted_storage_snapshot", None)
        config.pop("deleted_children_snapshot", None)
        hardware.device_config = config
        flag_modified(hardware, "device_config")
        self.session.flush()

    def _restore_children_from_snapshot(
        self, chassis: Device, children_snapshot: list
    ) -> list:
        """从机箱的 device_config 快照重建子节点（含硬件/NIC/存储）

        优先恢复已软删除的原子节点（按 device_id 或 device_name 匹配），
        仅当原子节点不存在时才创建新 Device，避免重复创建。

        Args:
            chassis: 已恢复的机箱设备
            children_snapshot: deleted_children_snapshot 列表

        Returns:
            已恢复的子节点 Device 列表
        """
        from app.models.device import Device
        from app.models.device_server_ext import DeviceServerExt
        from app.models.device_hardware import DeviceHardware
        from app.models.device_nics_port import DeviceNicsPort
        from app.models.device_storage import DeviceStorage

        session = self.session
        restored = []

        for snap in children_snapshot:
            snap_device_id = snap.get("device_id")
            snap_device_name = snap.get("device_name")

            child = None
            if snap_device_id:
                child = session.query(Device).filter(
                    Device.id == snap_device_id
                ).first()

            if not child and snap_device_name:
                child = session.query(Device).filter(
                    Device.device_name == snap_device_name,
                    Device.deleted_at.isnot(None),  # 只匹配已软删除的
                ).first()

            if child:
                child.deleted_at = None
                child.status = DeviceStatus.AVAILABLE
                child.cabinet_id = chassis.cabinet_id
                child.customer_id = chassis.customer_id
                if snap.get("height_u"):
                    child.height_u = snap.get("height_u")
                if child.server_ext:
                    child.server_ext.parent_device_id = chassis.id
                    child.server_ext.node_position = snap.get("node_position")
                    child.server_ext.node_row = snap.get("node_row")
                    child.server_ext.node_col = snap.get("node_col")
                logger.info("恢复已有子节点: device_id=%d, name=%s", child.id, child.device_name)
            else:
                child = Device(
                    device_name=snap_device_name or f"{chassis.device_name}-Node{snap.get('node_position', '?')}",
                    device_type="server",
                    device_subtype="node",
                    serial_number=snap.get("serial_number"),
                    management_ip=snap.get("management_ip"),
                    height_u=snap.get("height_u"),
                    cabinet_id=chassis.cabinet_id,
                    customer_id=chassis.customer_id,
                    brand=chassis.brand,
                    device_model=chassis.device_model,
                    status=DeviceStatus.AVAILABLE,
                )
                session.add(child)
                session.flush()

                server_ext = DeviceServerExt(
                    device_id=child.id,
                    parent_device_id=chassis.id,
                    is_chassis=False,
                    node_position=snap.get("node_position"),
                    node_row=snap.get("node_row"),
                    node_col=snap.get("node_col"),
                )
                session.add(server_ext)

                _HW_RESTORE_FIELDS = frozenset({
                    "cpu", "cpu_way", "cpu_cores", "cpu_template_id",
                    "memory", "memory_size_gb", "memory_template_id",
                    "gpu", "gpu_count", "gpu_template_id",
                    "storage_summary", "os_version",
                    "ipmi_address",  # ipmi_password/ipmi_username 不在白名单中
                })
                hw_data = snap.get("hardware") or {}
                if hw_data:
                    safe_hw = {k: v for k, v in hw_data.items()
                               if k in _HW_RESTORE_FIELDS and v is not None}
                    hw = DeviceHardware(device_id=child.id, **safe_hw)
                else:
                    hw = DeviceHardware(device_id=child.id)
                session.add(hw)

                _NIC_RESTORE_FIELDS = frozenset({
                    "nic_number", "nic_name", "port_number", "port_name",
                    "port_type", "port_speed", "port_status", "template_id", "description",
                })
                for nic in snap.get("nics", []):
                    session.add(DeviceNicsPort(
                        device_id=child.id,
                        **{k: v for k, v in nic.items() if k in _NIC_RESTORE_FIELDS and v is not None}
                    ))

                _STORAGE_RESTORE_FIELDS = frozenset({
                    "storage_type", "model", "capacity", "capacity_gb",
                    "interface_type", "manufacturer", "slot_number",
                    "template_id", "serial_number",
                })
                for st in snap.get("storage", []):
                    safe_st = {k: v for k, v in st.items()
                               if k in _STORAGE_RESTORE_FIELDS and v is not None}
                    session.add(DeviceStorage(device_id=child.id, **safe_st))

                logger.info("从快照重建子节点: device_id=%d, name=%s", child.id, child.device_name)

            restored.append(child)

        session.flush()
        return restored

    def _update_cabinet_usage(self, cabinet_id: int) -> bool:
        """更新机柜使用情况（通过 cabinet_service 避免循环依赖）"""
        try:
            from app.services.cabinet_service import cabinet_service

            return cabinet_service.update_cabinet_usage(cabinet_id)
        except ImportError:
            logger.warning("无法导入 cabinet_service，跳过机柜使用情况更新: cabinet_id=%d", cabinet_id)
            return False


device_service = DeviceService(DeviceRepository())
