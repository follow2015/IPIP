# -*- coding: utf-8 -*-
"""
核心枚举定义（前端枚举的单一真相源）

本文件是后端状态枚举的唯一真相源。前端枚举由
scripts/generate_frontend_enums.py 读取本文件的 GENERATED_ENUMS / STATUS_DISPLAY
注册表自动生成 frontend-new/src/types/status-codes.generated.ts。

修改状态编码/中文标签/颜色，请只改此处，然后运行：
    python scripts/generate_frontend_enums.py            # 重新生成前端枚举
    python scripts/generate_frontend_enums.py --check    # CI 校验，不写文件

注意：只有放进 GENERATED_ENUMS 的枚举才会同步到前端；其余（如 DataSource）仅后端使用，不进生成。
"""
from enum import IntEnum, Enum
from typing import List


class IPStatus(IntEnum):
    ACTIVE = 0
    INACTIVE = 1
    BANNED = 2
    UNUSED = 3
    PENDING_BAN = 4
    PENDING_UNBAN = 5


class UserStatus(IntEnum):
    ACTIVE = 0
    INACTIVE = 1


class RouteNotes(IntEnum):
    DEFAULT = 0
    INTERCONNECT = 1
    SUBNET = 2
    NETWORK = 3
    BLACKHOLE = 4
    GATEWAY = 5
    NEXTHOP = 6


class SwitchStatus(IntEnum):
    CORE = 0
    ACCESS = 1

TOMBSTONE = "__tombstone__"


class SeverityLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ChannelType(str, Enum):
    INBOX = "inbox"
    EMAIL = "email"
    WECHAT_WORK = "wechat_work"
    FEISHU = "feishu"
    CUSTOM = "custom"


PERSONAL_CHANNELS = (ChannelType.INBOX, ChannelType.EMAIL)

BROADCAST_CHANNELS = (ChannelType.WECHAT_WORK, ChannelType.FEISHU, ChannelType.CUSTOM)


class DataSource:
    MANUAL = "manual"
    AUTO = "auto"
    HYBRID = "hybrid"


class DeviceStatus:

    SCRAPPED = 0
    AVAILABLE = 1
    ONLINE = 2
    OFFLINE = 3
    MAINTENANCE = 4
    RESERVED = 5
    PENDING_ONLINE = 6
    TESTING = 7

    ALLOWED_TRANSITIONS = {
        AVAILABLE:       [RESERVED, ONLINE, PENDING_ONLINE, MAINTENANCE, SCRAPPED],
        RESERVED:        [ONLINE, PENDING_ONLINE, AVAILABLE, SCRAPPED],
        ONLINE:          [OFFLINE, MAINTENANCE, TESTING, SCRAPPED],
        OFFLINE:         [ONLINE, MAINTENANCE, AVAILABLE, SCRAPPED],
        MAINTENANCE:     [ONLINE, OFFLINE, SCRAPPED],
        PENDING_ONLINE:  [ONLINE, AVAILABLE, SCRAPPED],
        TESTING:         [ONLINE, OFFLINE, MAINTENANCE, SCRAPPED],
        SCRAPPED:        [],
    }

    STATUS_NAMES = {
        0: "已报废",
        1: "可用",
        2: "在线",
        3: "离线",
        4: "维护中",
        5: "预留",
        6: "待上线",
        7: "测试中",
    }

    @classmethod
    def can_transition(cls, from_status: int, to_status: int) -> bool:
        return to_status in cls.ALLOWED_TRANSITIONS.get(from_status, [])

    @classmethod
    def active_statuses(cls) -> List[int]:
        return [cls.AVAILABLE, cls.ONLINE, cls.OFFLINE, cls.MAINTENANCE,
                cls.RESERVED, cls.PENDING_ONLINE, cls.TESTING]


class VLANStatus(IntEnum):
    INACTIVE = 0
    ACTIVE = 1
    RESERVED = 2


class LAGStatus(IntEnum):
    INACTIVE = 0
    ACTIVE = 1
    DEGRADED = 2


class CustomerStatus(IntEnum):
    ACTIVE = 0
    DISABLED = 1
    PENDING = 2
    TERMINATED = 3


class RoomStatus(IntEnum):
    NORMAL = 0
    DISABLED = 1


class CabinetStatus(IntEnum):
    DISABLED = 0
    AVAILABLE = 1
    IN_USE = 2
    MAINTENANCE = 3
    RESERVED = 4


class NotificationTypeCode(str, Enum):
    DEVICE_UNREACHABLE = "device_unreachable"
    DEVICE_RECOVERED = "device_recovered"
    TEMPERATURE_ALERT = "temperature_alert"
    DISK_FAILURE_ALERT = "disk_failure_alert"
    PORT_STATUS_CHANGED = "port_status_changed"
    MONITOR_INTERRUPTED = "monitor_interrupted"
    RAID_FAILURE_ALERT = "raid_failure_alert"
    BATCH_CREATE_DEVICES = "batch_create_devices"
    BATCH_BAN_IP = "batch_ban_ip"
    BATCH_UNBAN_IP = "batch_unban_ip"
    IP_SCAN_COMPLETE = "ip_scan_complete"
    IP_SCAN_FAILED = "ip_scan_failed"
    ROOM_SCAN_COMPLETE = "room_scan_complete"
    ROOM_SCAN_FAILED = "room_scan_failed"
    VIRTUAL_ROOM_SCAN_COMPLETE = "virtual_room_scan_complete"
    VIRTUAL_ROOM_SCAN_FAILED = "virtual_room_scan_failed"
    PORT_ACTION = "port_action"
    ASYNC_ACTION = "async_action"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class ProbeErrorCode(str, Enum):
    TIMEOUT = "timeout"
    PROBE_TIMEOUT = "probe_timeout"
    PROBE_ERROR = "probe_error"
    NO_MANAGEMENT_IP = "no_management_ip"
    DNS_RESOLVE_TIMEOUT = "dns_resolve_timeout"
    AUTH_FAILED = "auth_failed"
    AUTH_ERROR = "auth_error"
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_ERROR = "connection_error"
    NETWORK_ERROR = "network_error"
    SSL_ERROR = "ssl_error"
    TLS_INCOMPATIBLE = "tls_incompatible"
    IPMI_ERROR = "ipmi_error"
    IPMI_NO_DATA = "no_data"
    UNKNOWN = "unknown"
    NO_HOST_REF = "no_host_ref"
    NO_API_URL = "no_api_url"
    ZABBIX_API_ERROR = "zabbix_api_error"
    ZABBIX_EMPTY_HOST_LIST = "zabbix_empty_host_list"
    HOST_NOT_IN_ZABBIX = "host_not_in_zabbix"


STATUS_DISPLAY = {
    IPStatus: {
        IPStatus.ACTIVE: ("活跃", "green"),
        IPStatus.INACTIVE: ("非活跃", "default"),
        IPStatus.BANNED: ("封禁", "red"),
        IPStatus.UNUSED: ("未使用", "blue"),
        IPStatus.PENDING_BAN: ("封禁中", "orange"),
        IPStatus.PENDING_UNBAN: ("解封中", "orange"),
    },
    RouteNotes: {
        RouteNotes.DEFAULT: ("默认路由", "default"),
        RouteNotes.INTERCONNECT: ("互联地址", "blue"),
        RouteNotes.SUBNET: ("子网路由", "green"),
        RouteNotes.NETWORK: ("网络路由", "cyan"),
        RouteNotes.BLACKHOLE: ("黑洞路由", "red"),
        RouteNotes.GATEWAY: ("网关地址", "purple"),
        RouteNotes.NEXTHOP: ("下一跳地址", "orange"),
    },
    SwitchStatus: {
        SwitchStatus.CORE: ("核心交换机", "blue"),
        SwitchStatus.ACCESS: ("接入交换机", "green"),
    },
    DeviceStatus: {
        DeviceStatus.SCRAPPED: ("已报废", "default"),
        DeviceStatus.AVAILABLE: ("可用", "blue"),
        DeviceStatus.ONLINE: ("在线", "green"),
        DeviceStatus.OFFLINE: ("离线", "red"),
        DeviceStatus.MAINTENANCE: ("维护中", "orange"),
        DeviceStatus.RESERVED: ("预留", "purple"),
        DeviceStatus.PENDING_ONLINE: ("待上线", "cyan"),
        DeviceStatus.TESTING: ("测试中", "geekblue"),
    },
    CustomerStatus: {
        CustomerStatus.ACTIVE: ("活跃", "green"),
        CustomerStatus.DISABLED: ("停用", "red"),
        CustomerStatus.PENDING: ("待审核", "orange"),
        CustomerStatus.TERMINATED: ("终止", "default"),
    },
    RoomStatus: {
        RoomStatus.NORMAL: ("正常", "green"),
        RoomStatus.DISABLED: ("停用", "red"),
    },
    CabinetStatus: {
        CabinetStatus.DISABLED: ("禁用", "red"),
        CabinetStatus.AVAILABLE: ("可用", "green"),
        CabinetStatus.IN_USE: ("使用中", "blue"),
        CabinetStatus.MAINTENANCE: ("维护中", "orange"),
        CabinetStatus.RESERVED: ("已预留", "purple"),
    },
    VLANStatus: {
        VLANStatus.INACTIVE: ("禁用", "red"),
        VLANStatus.ACTIVE: ("正常", "green"),
        VLANStatus.RESERVED: ("预留", "orange"),
    },
    UserStatus: {
        UserStatus.ACTIVE: ("活跃", "green"),
        UserStatus.INACTIVE: ("禁用", "red"),
    },
    LAGStatus: {
        LAGStatus.INACTIVE: ("禁用", "red"),
        LAGStatus.ACTIVE: ("正常", "green"),
        LAGStatus.DEGRADED: ("降级", "orange"),
    },
    NotificationTypeCode: {
        NotificationTypeCode.DEVICE_UNREACHABLE: ("设备不可达", "red"),
        NotificationTypeCode.DEVICE_RECOVERED: ("设备恢复", "green"),
        NotificationTypeCode.BATCH_CREATE_DEVICES: ("批量创建设备", "blue"),
        NotificationTypeCode.BATCH_BAN_IP: ("批量封禁IP", "orange"),
        NotificationTypeCode.BATCH_UNBAN_IP: ("批量解封IP", "green"),
        NotificationTypeCode.IP_SCAN_COMPLETE: ("IP扫描完成", "green"),
        NotificationTypeCode.IP_SCAN_FAILED: ("IP扫描失败", "red"),
        NotificationTypeCode.ROOM_SCAN_COMPLETE: ("机房扫描完成", "green"),
        NotificationTypeCode.ROOM_SCAN_FAILED: ("机房扫描失败", "red"),
        NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE: ("虚拟机房扫描完成", "green"),
        NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED: ("虚拟机房扫描失败", "red"),
        NotificationTypeCode.PORT_ACTION: ("端口操作结果", "blue"),
        NotificationTypeCode.ASYNC_ACTION: ("异步操作结果", "blue"),
        NotificationTypeCode.RATE_LIMIT_EXCEEDED: ("频率超限", "orange"),
        NotificationTypeCode.TEMPERATURE_ALERT: ("温度告警", "volcano"),
        NotificationTypeCode.DISK_FAILURE_ALERT: ("硬盘故障", "red"),
        NotificationTypeCode.PORT_STATUS_CHANGED: ("端口状态变化", "purple"),
        NotificationTypeCode.MONITOR_INTERRUPTED: ("监控中断", "orange"),
        NotificationTypeCode.RAID_FAILURE_ALERT: ("RAID故障", "magenta"),
    },
    ProbeErrorCode: {
        ProbeErrorCode.TIMEOUT: ("超时", "orange"),
        ProbeErrorCode.PROBE_TIMEOUT: ("探测超时", "red"),
        ProbeErrorCode.PROBE_ERROR: ("探测异常", "red"),
        ProbeErrorCode.NO_MANAGEMENT_IP: ("无管理IP", "default"),
        ProbeErrorCode.DNS_RESOLVE_TIMEOUT: ("DNS解析超时", "orange"),
        ProbeErrorCode.AUTH_FAILED: ("认证失败", "red"),
        ProbeErrorCode.AUTH_ERROR: ("认证失败", "red"),
        ProbeErrorCode.CONNECTION_REFUSED: ("连接被拒绝", "red"),
        ProbeErrorCode.CONNECTION_ERROR: ("连接错误", "red"),
        ProbeErrorCode.NETWORK_ERROR: ("网络错误", "red"),
        ProbeErrorCode.SSL_ERROR: ("SSL错误", "red"),
        ProbeErrorCode.TLS_INCOMPATIBLE: ("TLS不兼容", "red"),
        ProbeErrorCode.IPMI_ERROR: ("IPMI错误", "red"),
        ProbeErrorCode.IPMI_NO_DATA: ("IPMI无数据", "orange"),
        ProbeErrorCode.UNKNOWN: ("未知错误", "default"),
        ProbeErrorCode.NO_HOST_REF: ("无主机引用", "default"),
        ProbeErrorCode.NO_API_URL: ("无API地址", "default"),
        ProbeErrorCode.ZABBIX_API_ERROR: ("Zabbix API错误", "red"),
        ProbeErrorCode.ZABBIX_EMPTY_HOST_LIST: ("Zabbix主机列表为空", "orange"),
        ProbeErrorCode.HOST_NOT_IN_ZABBIX: ("主机不在Zabbix中", "orange"),
    },
}


GENERATED_ENUMS = [
    (IPStatus, "IPStatusCode", "IP_STATUS_MAP", "IP_STATUS_OPTIONS", "IPStatusCode"),
    (RouteNotes, "RouteNotesCode", "ROUTE_NOTES_MAP", None, "number"),
    (SwitchStatus, "SwitchRoleCode", "SWITCH_ROLE_MAP", None, "SwitchRoleCode"),
    (DeviceStatus, "DeviceStatusCode", "DEVICE_STATUS_MAP", "DEVICE_STATUS_OPTIONS", "DeviceStatusCode"),
    (CustomerStatus, "CustomerStatusCode", "CUSTOMER_STATUS_MAP", "CUSTOMER_STATUS_OPTIONS", "CustomerStatusCode"),
    (RoomStatus, "RoomStatusCode", "ROOM_STATUS_MAP", "ROOM_STATUS_OPTIONS", "RoomStatusCode"),
    (CabinetStatus, "CabinetStatusCode", "CABINET_STATUS_MAP", "CABINET_STATUS_OPTIONS", "CabinetStatusCode"),
    (VLANStatus, "VLANStatusCode", "VLAN_STATUS_MAP", None, "number"),
    (UserStatus, "UserStatusCode", "USER_STATUS_MAP", "USER_STATUS_OPTIONS", "UserStatusCode"),
    (LAGStatus, "LAGStatusCode", "LAG_STATUS_MAP", None, "number"),
    (NotificationTypeCode, "NotificationTypeCode", None, "NOTIFICATION_TYPE_OPTIONS", "NotificationTypeCode"),
    (ProbeErrorCode, "ProbeErrorCode", "PROBE_ERROR_MAP", None, "ProbeErrorCode"),
]


NOTIFICATION_TYPE_GROUPS = [
    ("监控告警", [NotificationTypeCode.DEVICE_UNREACHABLE, NotificationTypeCode.DEVICE_RECOVERED,
                NotificationTypeCode.TEMPERATURE_ALERT, NotificationTypeCode.DISK_FAILURE_ALERT,
                NotificationTypeCode.PORT_STATUS_CHANGED, NotificationTypeCode.MONITOR_INTERRUPTED,
                NotificationTypeCode.RAID_FAILURE_ALERT]),
    ("操作结果", [NotificationTypeCode.BATCH_CREATE_DEVICES, NotificationTypeCode.BATCH_BAN_IP, NotificationTypeCode.BATCH_UNBAN_IP]),
    ("扫描完成", [NotificationTypeCode.IP_SCAN_COMPLETE, NotificationTypeCode.IP_SCAN_FAILED,
                NotificationTypeCode.ROOM_SCAN_COMPLETE, NotificationTypeCode.ROOM_SCAN_FAILED,
                NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE, NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED]),
    ("端口/异步操作", [NotificationTypeCode.PORT_ACTION, NotificationTypeCode.ASYNC_ACTION]),
    ("运维告警", [NotificationTypeCode.RATE_LIMIT_EXCEEDED]),
]

NOTIFICATION_TYPE_LABELS = {
    NotificationTypeCode.DEVICE_UNREACHABLE: "设备不可达",
    NotificationTypeCode.DEVICE_RECOVERED: "设备恢复",
    NotificationTypeCode.BATCH_CREATE_DEVICES: "批量创建设备",
    NotificationTypeCode.BATCH_BAN_IP: "批量封禁IP",
    NotificationTypeCode.BATCH_UNBAN_IP: "批量解封IP",
    NotificationTypeCode.IP_SCAN_COMPLETE: "IP扫描完成",
    NotificationTypeCode.IP_SCAN_FAILED: "IP扫描失败",
    NotificationTypeCode.ROOM_SCAN_COMPLETE: "机房扫描完成",
    NotificationTypeCode.ROOM_SCAN_FAILED: "机房扫描失败",
    NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE: "虚拟机房扫描完成",
    NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED: "虚拟机房扫描失败",
    NotificationTypeCode.PORT_ACTION: "端口操作结果",
    NotificationTypeCode.ASYNC_ACTION: "异步操作结果",
    NotificationTypeCode.RATE_LIMIT_EXCEEDED: "频率超限",
}


class DeviceSubtypeCode(str, Enum):
    STANDALONE = "standalone"
    CHASSIS = "chassis"
    NODE = "node"
    STORAGE = "storage"
    GPU = "gpu"
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    PDU = "pdu"
    UPS = "ups"
    OTHER = "other"


class SwitchDeviceTypeCode(str, Enum):
    HUAWEI = "huawei"
    H3C = "h3c"
    CISCO = "cisco"


class SSHProtocolCode(str, Enum):
    SSH = "ssh"
    TELNET = "telnet"


class MonitorProtocolCode(str, Enum):
    SNMP = "snmp"
    IPMI = "ipmi"
    ZABBIX = "zabbix"
    PING = "ping"


DEVICE_IMPORT_CN_TO_EN = {
    "设备名称": "device_name", "设备类型": "device_type", "设备子类型": "device_subtype",
    "品牌": "brand", "设备型号": "device_model", "序列号": "serial_number",
    "主机名": "hostname", "管理IP": "management_ip", "MAC地址": "mac_address",
    "IP地址": "ip_address", "机柜ID": "cabinet_id", "U位": "u_position",
    "高度U": "height_u", "状态": "status", "备注": "notes",
    "CPU": "cpu", "CPU路数": "cpu_way", "CPU核数": "cpu_cores",
    "内存": "memory", "内存容量GB": "memory_size_gb",
    "存储": "storage", "存储概要": "storage_summary", "操作系统": "os_version",
    "GPU": "gpu", "GPU数量": "gpu_count",
    "CPU模板ID": "cpu_template_id", "内存模板ID": "memory_template_id",
    "内存条数": "memory_dimm_count", "GPU模板ID": "gpu_template_id",
    "存储模板ID": "storage_template_id", "网卡模板ID": "nic_template_id",
    "IPMI地址": "ipmi_address", "IPMI用户名": "ipmi_username", "IPMI密码": "ipmi_password",
    "客户ID": "customer_id", "负责人": "responsible_person", "功率": "power",
    "资产编号": "asset_number", "供应商": "supplier", "供应商联系方式": "supplier_contact",
    "合同编号": "contract_number", "采购日期": "purchase_date", "采购价格": "purchase_price",
    "发票号": "invoice_number", "保修开始": "warranty_start", "保修结束": "warranty_end",
    "保修类型": "warranty_type", "上线日期": "online_date", "下线日期": "offline_date",
    "生命周期年": "lifecycle_years", "是否机箱": "is_chassis", "节点行数": "node_rows",
    "节点列数": "node_cols", "自动创建节点": "auto_create_nodes",
    "节点命名规则": "node_naming_pattern", "节点总数": "total_nodes",
    "父设备ID": "parent_device_id", "节点位置": "node_position",
    "节点行": "node_row", "节点列": "node_col",
    "所属机箱名称": "parent_device_name",
    "是否网管": "is_managed", "SSH管理IP": "ssh_ip", "SSH端口": "ssh_port",
    "SSH用户名": "ssh_username", "SSH密码": "ssh_password",
    "驱动类型": "ssh_device_type", "连接协议": "ssh_protocol",
    "交换机角色": "switch_role", "端口数量": "port_num",
}

EN_TO_CN_DEVICE_IMPORT = {v: k for k, v in DEVICE_IMPORT_CN_TO_EN.items()}

CABINET_IMPORT_CN_TO_EN = {
    "机柜名称": "name", "机房ID": "room_id", "位置": "location",
    "行": "row", "列": "col", "U位容量": "total_u", "总功率": "total_power",
    "最大承重": "max_weight", "状态": "status", "客户ID": "customer_id", "备注": "notes",
}

EN_TO_CN_CABINET_IMPORT = {v: k for k, v in CABINET_IMPORT_CN_TO_EN.items()}

CUSTOMER_IMPORT_CN_TO_EN = {
    "客户名称": "name", "联系人": "contact_person", "联系电话": "contact_phone",
    "邮箱": "email", "地址": "address", "备注": "notes",
}

EN_TO_CN_CUSTOMER_IMPORT = {v: k for k, v in CUSTOMER_IMPORT_CN_TO_EN.items()}
