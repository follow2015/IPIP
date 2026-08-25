# -*- coding: utf-8 -*-
"""
设备导入导出编排层

从 app/api/device.py 拆分而来，承载无 Flask 依赖的纯业务逻辑，
使导入导出核心首次可脱离 HTTP 上下文进行单元测试。

保持与原始实现完全一致的外部行为（字段、顺序、错误语义）。
"""

import pandas as pd
from io import BytesIO

from app.utils.logging import get_logger
from app.services import DeviceService
from app.persistence.device_repository import DeviceRepository
from app.core.enums import (
    DEVICE_IMPORT_CN_TO_EN, EN_TO_CN_DEVICE_IMPORT,
    SwitchDeviceTypeCode, SSHProtocolCode, DeviceSubtypeCode, SwitchStatus,
)
from app.utils import validation_manager
from app.schemas.device import DeviceCreateSchema
from app.services.network_device_service import NetworkDeviceService
from app.models.device import Device
from app.models.device_server_ext import DeviceServerExt
from app.exceptions.business import DeviceNotSupported, InvalidOperationError
from app.exceptions.data_access import RecordNotFoundError
from app.exceptions.validation import RequiredFieldError, InvalidFormatError

logger = get_logger(__name__)

VALID_SSH_DEVICE_TYPES = {e.value for e in SwitchDeviceTypeCode}
VALID_SSH_PROTOCOLS = {e.value for e in SSHProtocolCode}
VALID_DEVICE_SUBTYPES = {e.value for e in DeviceSubtypeCode}
VALID_SWITCH_ROLES = {e.value for e in SwitchStatus}

device_service = DeviceService(DeviceRepository())


class EmptyExportError(InvalidOperationError):
    """导出时没有任何设备数据。"""

    def __init__(self, message: str = "没有可导出的设备数据"):
        super().__init__(operation="export_devices", reason=message, message=message)
        self.status_code = 404


def build_import_template(template_type: str) -> BytesIO:
    """生成设备导入模板字节流（按设备类型拆分，含表头+示例行）。

    Args:
        template_type: 设备类型（server/network/other），默认 server

    Returns:
        可被 flask.send_file 直接消费的 BytesIO 缓冲
    """
    template_type = (template_type or "server").lower()

    if template_type == "server":
        columns = [
            "device_name", "device_subtype", "brand", "device_model",
            "serial_number", "hostname", "management_ip", "mac_address", "ip_address",
            "cabinet_id", "u_position", "height_u", "status", "notes",
            "cpu_template_id", "memory_template_id", "memory_dimm_count",
            "gpu_template_id", "gpu_count",
            "storage_template_id", "nic_template_id", "os_version",
            "ipmi_address", "ipmi_username", "ipmi_password",
            "customer_id", "responsible_person", "power",
            "asset_number", "supplier", "supplier_contact", "contract_number",
            "purchase_date", "purchase_price", "invoice_number",
            "warranty_start", "warranty_end", "warranty_type",
            "online_date", "offline_date", "lifecycle_years",
            "is_chassis", "node_rows", "node_cols", "auto_create_nodes",
            "node_naming_pattern", "total_nodes",
            "parent_device_name", "parent_device_id", "node_position", "node_row", "node_col",
        ]
        example_rows = [
            {
                "device_name": "SRV-001", "device_subtype": "standalone",
                "brand": "华为", "device_model": "RH2288H V5", "serial_number": "SN210001",
                "hostname": "srv-001", "management_ip": "192.168.1.10", "mac_address": "", "ip_address": "",
                "cabinet_id": 1, "u_position": 1, "height_u": 2, "status": 1, "notes": "业务服务器",
                "cpu_template_id": 1, "memory_template_id": 2, "memory_dimm_count": 8,
                "gpu_template_id": "", "gpu_count": "",
                "storage_template_id": "", "nic_template_id": "", "os_version": "CentOS 7.9",
                "ipmi_address": "10.0.0.1", "ipmi_username": "", "ipmi_password": "",
                "customer_id": "", "responsible_person": "", "power": 800,
                "asset_number": "IT-2024-001", "supplier": "华为", "supplier_contact": "", "contract_number": "",
                "purchase_date": "2024-01-15", "purchase_price": "", "invoice_number": "",
                "warranty_start": "2024-01-15", "warranty_end": "2027-01-15", "warranty_type": "",
                "online_date": "", "offline_date": "", "lifecycle_years": "",
                "is_chassis": "", "node_rows": "", "node_cols": "", "auto_create_nodes": "",
                "node_naming_pattern": "", "total_nodes": "",
                "parent_device_name": "", "parent_device_id": "", "node_position": "", "node_row": "", "node_col": "",
            },
            {
                "device_name": "CHS-001", "device_subtype": "chassis",
                "brand": "华为", "device_model": "E9000", "serial_number": "SN210002",
                "hostname": "", "management_ip": "10.0.0.2", "mac_address": "", "ip_address": "",
                "cabinet_id": 1, "u_position": 10, "height_u": 8, "status": 2, "notes": "刀片机箱",
                "cpu_template_id": "", "memory_template_id": "", "memory_dimm_count": "",
                "gpu_template_id": "", "gpu_count": "",
                "storage_template_id": "", "nic_template_id": "", "os_version": "",
                "ipmi_address": "", "ipmi_username": "", "ipmi_password": "",
                "customer_id": "", "responsible_person": "", "power": 2000,
                "asset_number": "", "supplier": "", "supplier_contact": "", "contract_number": "",
                "purchase_date": "", "purchase_price": "", "invoice_number": "",
                "warranty_start": "", "warranty_end": "", "warranty_type": "",
                "online_date": "", "offline_date": "", "lifecycle_years": "",
                "is_chassis": True, "node_rows": 2, "node_cols": 4, "auto_create_nodes": True,
                "node_naming_pattern": "{chassis}-Node{pos}", "total_nodes": 8,
                "parent_device_name": "", "parent_device_id": "", "node_position": "", "node_row": "", "node_col": "",
            },
            {
                "device_name": "CHS-001-Node1", "device_subtype": "node",
                "brand": "华为", "device_model": "CH121 V5", "serial_number": "SN210003",
                "hostname": "", "management_ip": "", "mac_address": "", "ip_address": "",
                "cabinet_id": "", "u_position": 0, "height_u": 0, "status": 2, "notes": "机箱子节点",
                "cpu_template_id": 3, "memory_template_id": 4, "memory_dimm_count": 4,
                "gpu_template_id": "", "gpu_count": "",
                "storage_template_id": "", "nic_template_id": "", "os_version": "",
                "ipmi_address": "", "ipmi_username": "", "ipmi_password": "",
                "customer_id": "", "responsible_person": "", "power": "",
                "asset_number": "", "supplier": "", "supplier_contact": "", "contract_number": "",
                "purchase_date": "", "purchase_price": "", "invoice_number": "",
                "warranty_start": "", "warranty_end": "", "warranty_type": "",
                "online_date": "", "offline_date": "", "lifecycle_years": "",
                "is_chassis": "", "node_rows": "", "node_cols": "", "auto_create_nodes": "",
                "node_naming_pattern": "", "total_nodes": "",
                "parent_device_name": "CHS-001", "parent_device_id": "", "node_position": 1, "node_row": 1, "node_col": 1,
            },
        ]
        sheet_name = "服务器导入模板"

    elif template_type == "network":
        columns = [
            "device_name", "device_subtype", "brand", "device_model",
            "serial_number", "hostname", "management_ip", "mac_address",
            "cabinet_id", "u_position", "height_u", "status", "notes", "os_version",
            "is_managed", "ssh_ip", "ssh_port", "ssh_username", "ssh_password",
            "ssh_device_type", "ssh_protocol",
            "switch_role", "port_num",
            "customer_id", "responsible_person", "power", "asset_number",
        ]
        example_rows = [
            {
                "device_name": "SW-001", "device_subtype": "switch",
                "brand": "华为", "device_model": "CE6800", "serial_number": "SN210004",
                "hostname": "sw-core-01", "management_ip": "192.168.1.254", "mac_address": "",
                "cabinet_id": 1, "u_position": 20, "height_u": 1, "status": 2, "notes": "核心交换机", "os_version": "VRP V8.8",
                "is_managed": True, "ssh_ip": "10.0.0.254", "ssh_port": 22, "ssh_username": "admin", "ssh_password": "admin123",
                "ssh_device_type": SwitchDeviceTypeCode.HUAWEI, "ssh_protocol": "ssh",
                "switch_role": 0, "port_num": 48,
                "customer_id": "", "responsible_person": "", "power": 350, "asset_number": "",
            },
            {
                "device_name": "SW-002", "device_subtype": "switch",
                "brand": "TP-LINK", "device_model": "TL-SG3428", "serial_number": "SN210005",
                "hostname": "", "management_ip": "", "mac_address": "",
                "cabinet_id": 1, "u_position": 21, "height_u": 1, "status": 2, "notes": "接入交换机", "os_version": "",
                "is_managed": "", "ssh_ip": "", "ssh_port": "", "ssh_username": "", "ssh_password": "",
                "ssh_device_type": "", "ssh_protocol": "",
                "switch_role": "", "port_num": "",
                "customer_id": "", "responsible_person": "", "power": 150, "asset_number": "",
            },
            {
                "device_name": "FW-001", "device_subtype": "firewall",
                "brand": "山石", "device_model": "SG6000", "serial_number": "SN210006",
                "hostname": "", "management_ip": "192.168.1.1", "mac_address": "",
                "cabinet_id": 1, "u_position": 22, "height_u": 1, "status": 2, "notes": "边界防火墙", "os_version": "",
                "is_managed": True, "ssh_ip": "10.0.0.1", "ssh_port": 22, "ssh_username": "admin", "ssh_password": "",
                "ssh_device_type": SwitchDeviceTypeCode.H3C, "ssh_protocol": "ssh",
                "switch_role": "", "port_num": "",
                "customer_id": "", "responsible_person": "", "power": 150, "asset_number": "",
            },
        ]
        sheet_name = "网络设备导入模板"

    else:
        columns = [
            "device_name", "device_subtype", "brand", "device_model",
            "serial_number", "cabinet_id", "u_position", "height_u", "status", "notes",
            "customer_id", "responsible_person", "power", "asset_number",
        ]
        example_rows = [
            {
                "device_name": "PDU-001", "device_subtype": "pdu",
                "brand": "", "device_model": "", "serial_number": "SN210007",
                "cabinet_id": 1, "u_position": 0, "height_u": 0, "status": 2, "notes": "电源分配单元",
                "customer_id": "", "responsible_person": "", "power": "", "asset_number": "",
            },
            {
                "device_name": "UPS-001", "device_subtype": "ups",
                "brand": "APC", "device_model": "Smart-UPS 3000", "serial_number": "SN210008",
                "cabinet_id": 1, "u_position": 0, "height_u": 2, "status": 2, "notes": "不间断电源",
                "customer_id": "", "responsible_person": "", "power": 3000, "asset_number": "",
            },
        ]
        sheet_name = "其他设备导入模板"

    df = pd.DataFrame(example_rows, columns=columns)
    cn_columns = [EN_TO_CN_DEVICE_IMPORT.get(col, col) for col in columns]
    df.columns = cn_columns
    buffer = BytesIO()

    brand_instructions = pd.DataFrame({
        "字段": ["品牌 (brand)"],
        "填写说明": [
            "请填写厂商的 enterprise 号（纯数字），与「监控 → OID 规则 → 厂商品牌」Tab 中的「enterprise_no」列一致。\n"
            "常见品牌参考：\n"
            "  服务器：2011=华为 / 674=Dell / 11=HP / 10876=Supermicro / 23=Lenovo\n"
            "  网络设备：9=思科 / 2011=华为 / 25506=H3C / 2636=Juniper / 3375=F5\n"
            "  存储：674=Dell EMC / 789=NetApp / 1991=Hitachi\n"
            "提示：可在「监控 → OID 规则 → 厂商品牌」Tab 查看完整列表及 enterprise_no。"
        ],
    })

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        brand_instructions.to_excel(writer, index=False, sheet_name="填写说明")
    buffer.seek(0)
    return buffer


_SUBTYPE_TO_TYPE = {
    "standalone": "server", "chassis": "server", "node": "server",
    "storage": "server", "gpu": "server",
    "switch": "network", "router": "network", "firewall": "network",
    "pdu": "other", "ups": "other", "other": "other",
}


IMPORT_TEXT_COLUMNS = {
    "device_name", "device_subtype", "brand", "device_model", "serial_number",
    "hostname", "management_ip", "mac_address", "ip_address", "notes", "os_version",
    "ipmi_address", "ipmi_username", "ipmi_password", "responsible_person",
    "asset_number", "supplier", "supplier_contact", "contract_number",
    "invoice_number", "node_naming_pattern", "parent_device_name",
}


def build_device_df(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """将上传的文件字节流解析为标准化 DataFrame。

    包含：扩展名选择解析方式、NaN 清洗、中文列名→英文列名映射、
    根据 device_subtype 自动推断 device_type。

    Args:
        file_bytes: 上传文件的原始字节
        filename: 原始文件名（用于判断 csv/xlsx）

    Returns:
        清洗并补全列后的 DataFrame
    """
    buf = BytesIO(file_bytes)
    fname = (filename or "").lower()
    if fname.endswith(".csv"):
        df = pd.read_csv(buf, encoding="utf-8-sig")
    else:
        df = pd.read_excel(buf)

    df = df.where(df.notna(), None)

    df.rename(columns=DEVICE_IMPORT_CN_TO_EN, inplace=True)

    for _col in IMPORT_TEXT_COLUMNS:
        if _col in df.columns:
            def _text_coerce(v):
                if pd.isna(v) or v is None:
                    return v
                if isinstance(v, float) and v.is_integer():
                    return str(int(v))
                return str(v)
            df[_col] = df[_col].apply(_text_coerce)

    if "device_type" not in df.columns and "device_subtype" in df.columns:
        df["device_type"] = df["device_subtype"].map(
            lambda s: _SUBTYPE_TO_TYPE.get(s, "") if s else ""
        )

    return df


def _expand_storage_nic_from_templates(device_id: int, storage_template_id, nic_template_id) -> None:
    """根据存储/网卡模板ID自动创建子记录（委托 DeviceService 的规范实现）。

    与手动添加设备共用同一套模板ID驱动逻辑：
    - 校验模板存在、类别正确（disk / nic）、未停用；
    - 按模板 spec 自动填充 storage_type / capacity_gb / interface_type 等字段；
    - 用 _format_capacity 生成可读容量（如 3840GB → 3.75TB）；
    - 网卡按模板 port_count 展开多端口。

    这样批量导入与页面添加在模板ID处理上行为完全一致，避免容量字段错填型号名等问题。

    Args:
        device_id: 已创建的设备ID
        storage_template_id: 存储配件模板ID（可为空，空则跳过）
        nic_template_id: 网卡配件模板ID（可为空，空则跳过）
    """
    from extensions import db

    if storage_template_id:
        try:
            sid = int(storage_template_id)
        except (ValueError, TypeError):
            sid = None
        if sid:
            device_service._create_storage_items(device_id, [{"template_id": sid}])

    if nic_template_id:
        try:
            nid = int(nic_template_id)
        except (ValueError, TypeError):
            nid = None
        if nid:
            device_service._create_nic_ports(device_id, [{"template_id": nid}])

    db.session.flush()


def parse_and_import_devices(df: pd.DataFrame) -> dict:
    """两遍导入核心：先建非节点设备建立 name→id 映射，再建节点设备。

    Args:
        df: 已由 build_device_df 处理好的 DataFrame

    Returns:
        {
            "imported_count": int,
            "failed_count": int,
            "failed_rows": [{"row", "device_name", "error"}, ...],
            "imported_ids": [int, ...],
        }

    Raises:
        ValueError: 缺少必需列（device_name）时抛出，供路由层转 400
    """
    required_columns = ["device_name"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise RequiredFieldError(missing_fields=missing_columns, message=f"缺少必需列: {', '.join(missing_columns)}")

    imported_count = 0
    failed_rows = []  # [{row, device_name, error}]
    imported_ids = []
    name_to_id = {}   # device_name → device_id（本文件内映射）

    for index, row in df.iterrows():
        try:
            device_data = {k: v for k, v in row.to_dict().items() if not pd.isna(v) and v is not None and v != ''}
            device_subtype = device_data.get("device_subtype", "")
            device_type = device_data.get("device_type", "")

            if device_subtype == "node":
                continue

            is_managed = device_data.pop("is_managed", None)
            ssh_ip = device_data.pop("ssh_ip", None)
            ssh_port = device_data.pop("ssh_port", None)
            ssh_username = device_data.pop("ssh_username", None)
            ssh_password = device_data.pop("ssh_password", None)
            ssh_device_type = device_data.pop("ssh_device_type", None)
            ssh_protocol = device_data.pop("ssh_protocol", None)
            switch_role = device_data.pop("switch_role", None)
            port_num = device_data.pop("port_num", None)

            if device_subtype and str(device_subtype).lower() not in VALID_DEVICE_SUBTYPES:
                raise InvalidFormatError(
                    field="device_subtype",
                    expected_format=f"可选值：{', '.join(sorted(VALID_DEVICE_SUBTYPES))}",
                    actual_value=device_subtype,
                    message=f"不支持的设备子类型：{device_subtype!r}。可选值：{', '.join(sorted(VALID_DEVICE_SUBTYPES))}"
                )
            if ssh_device_type and str(ssh_device_type).lower() not in VALID_SSH_DEVICE_TYPES:
                raise InvalidFormatError(
                    field="ssh_device_type",
                    expected_format=f"可选值：{', '.join(sorted(VALID_SSH_DEVICE_TYPES))}",
                    actual_value=ssh_device_type,
                    message=f"不支持的驱动类型：{ssh_device_type!r}。可选值：{', '.join(sorted(VALID_SSH_DEVICE_TYPES))}"
                )
            if ssh_protocol and str(ssh_protocol).lower() not in VALID_SSH_PROTOCOLS:
                raise InvalidFormatError(
                    field="ssh_protocol",
                    expected_format=f"可选值：{', '.join(sorted(VALID_SSH_PROTOCOLS))}",
                    actual_value=ssh_protocol,
                    message=f"不支持的连接协议：{ssh_protocol!r}。可选值：{', '.join(sorted(VALID_SSH_PROTOCOLS))}"
                )
            if switch_role is not None and switch_role != "":
                try:
                    role_val = int(switch_role)
                except (ValueError, TypeError):
                    raise InvalidFormatError(field="switch_role", expected_format="整数（0=核心，1=接入）", actual_value=switch_role, message=f"交换机角色必须为整数（0=核心，1=接入），当前值：{switch_role!r}")
                if role_val not in VALID_SWITCH_ROLES:
                    raise InvalidFormatError(field="switch_role", expected_format="0（核心）或 1（接入）", actual_value=role_val, message=f"不支持的交换机角色：{role_val}。可选值：0（核心）、1（接入）")

            device_data.pop("parent_device_name", None)

            if device_type == "server" or device_subtype in ("standalone", "chassis", "node"):
                for _text_field in ("cpu", "cpu_way", "cpu_cores",
                                    "memory", "memory_size_gb",
                                    "gpu", "storage", "storage_summary"):
                    device_data.pop(_text_field, None)

                if device_subtype in ("standalone", "node"):
                    if not device_data.get("cpu_template_id"):
                        raise RequiredFieldError(
                            missing_fields=["cpu_template_id"],
                            message=f"服务器设备（{device_subtype}）必须指定CPU模板ID（cpu_template_id），请在配件模板管理中创建CPU模板后填入对应ID"
                        )
                    if not device_data.get("memory_template_id"):
                        raise RequiredFieldError(
                            missing_fields=["memory_template_id"],
                            message=f"服务器设备（{device_subtype}）必须指定内存模板ID（memory_template_id），请在配件模板管理中创建内存模板后填入对应ID"
                        )

                _storage_tpl_id = device_data.pop("storage_template_id", None)
                _nic_tpl_id = device_data.pop("nic_template_id", None)
            else:
                _storage_tpl_id = None
                _nic_tpl_id = None

            validated = validation_manager.validate_schema(device_data, DeviceCreateSchema())

            if device_type == "network" and is_managed in (True, "true", "True", 1, "1") and ssh_ip:
                switch_config = {
                    "ip": ssh_ip,
                    "port": int(ssh_port) if ssh_port else 22,
                    "username": ssh_username or "",
                    "password": ssh_password or "",
                    "device_type": ssh_device_type,
                    "protocol": ssh_protocol or "ssh",
                }
                if switch_role is not None:
                    switch_config["switch_role"] = int(switch_role)
                if port_num is not None:
                    switch_config["port_num"] = int(port_num)
                nd_svc = NetworkDeviceService()
                device, _switch = nd_svc.create_network_device(validated, switch_config)
            else:
                device = device_service.create_device(validated)

            if device and device.id:
                _expand_storage_nic_from_templates(device.id, _storage_tpl_id, _nic_tpl_id)

            imported_count += 1
            if device and device.id:
                imported_ids.append(device.id)
                if device.device_name:
                    name_to_id[device.device_name] = device.id
        except Exception as e:
            logger.error("导入第 %d 行失败: %s", index + 1, str(e))
            failed_rows.append({
                "row": index + 1,
                "device_name": row.to_dict().get("device_name", ""),
                "error": str(e),
            })

    for index, row in df.iterrows():
        try:
            device_data = {k: v for k, v in row.to_dict().items() if not pd.isna(v) and v is not None and v != ''}
            device_subtype = device_data.get("device_subtype", "")

            if device_subtype != "node":
                continue

            parent_name = device_data.pop("parent_device_name", None)
            if parent_name and "parent_device_id" not in device_data:
                if parent_name in name_to_id:
                    device_data["parent_device_id"] = name_to_id[parent_name]
                else:
                    existing = Device.query.filter_by(device_name=str(parent_name)).first()
                    if existing and existing.is_chassis:
                        device_data["parent_device_id"] = existing.id
                    else:
                        raise RecordNotFoundError("device", identifier={"device_name": parent_name}, message=f"未找到名为 '{parent_name}' 的机箱设备")

            for _key in ("is_managed", "ssh_ip", "ssh_port", "ssh_username",
                         "ssh_password", "ssh_device_type", "ssh_protocol",
                         "switch_role", "port_num"):
                device_data.pop(_key, None)

            for _text_field in ("cpu", "cpu_way", "cpu_cores",
                                "memory", "memory_size_gb",
                                "gpu", "storage", "storage_summary"):
                device_data.pop(_text_field, None)

            if not device_data.get("cpu_template_id"):
                raise RequiredFieldError(
                    missing_fields=["cpu_template_id"],
                    message="节点设备必须指定CPU模板ID（cpu_template_id），请在配件模板管理中创建CPU模板后填入对应ID"
                )
            if not device_data.get("memory_template_id"):
                raise RequiredFieldError(
                    missing_fields=["memory_template_id"],
                    message="节点设备必须指定内存模板ID（memory_template_id），请在配件模板管理中创建内存模板后填入对应ID"
                )

            _node_storage_tpl_id = device_data.pop("storage_template_id", None)
            _node_nic_tpl_id = device_data.pop("nic_template_id", None)

            validated = validation_manager.validate_schema(device_data, DeviceCreateSchema())
            device = device_service.create_device(validated)

            if device and device.id:
                _expand_storage_nic_from_templates(device.id, _node_storage_tpl_id, _node_nic_tpl_id)

            imported_count += 1
            if device and device.id:
                imported_ids.append(device.id)
        except Exception as e:
            logger.error("导入第 %d 行(节点)失败: %s", index + 1, str(e))
            failed_rows.append({
                "row": index + 1,
                "device_name": row.to_dict().get("device_name", ""),
                "error": str(e),
            })

    return {
        "imported_count": imported_count,
        "failed_count": len(failed_rows),
        "failed_rows": failed_rows,
        "imported_ids": imported_ids,
    }


def export_devices_to_excel(cabinet_id=None, customer_id=None) -> BytesIO:
    """分页拼接全部设备并生成 Excel 字节流。

    Args:
        cabinet_id: 机柜ID过滤（可选）
        customer_id: 客户ID过滤（可选）

    Returns:
        可被 flask.send_file 直接消费的 BytesIO 缓冲

    Raises:
        EmptyExportError: 没有任何可导出的设备数据时
    """
    all_devices = []
    page = 1
    page_size = 5000
    while True:
        result = device_service.get_all_devices(
            cabinet_id=cabinet_id,
            customer_id=customer_id,
            page=page,
            page_size=page_size
        )
        devices = result.get("devices", [])
        if not devices:
            break
        all_devices.extend(devices)
        if len(devices) < page_size:
            break
        page += 1

    if not all_devices:
        raise EmptyExportError("没有可导出的设备数据")

    device_dicts = [d.to_dict() if hasattr(d, "to_dict") else d for d in all_devices]

    from app.services import import_export_service
    return import_export_service.export_to_excel(device_dicts, "设备数据")
