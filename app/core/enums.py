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
    """IP地址状态枚举"""
    ACTIVE = 0        # 活跃(在线)
    INACTIVE = 1      # 非活跃(离线)
    BANNED = 2        # 封禁(黑洞路由/静态ARP已生效)
    UNUSED = 3        # 未使用
    PENDING_BAN = 4   # 封禁中(SSH执行前/中，等待交换机确认)
    PENDING_UNBAN = 5 # 解封中(SSH执行前/中，等待交换机确认)


class UserStatus(IntEnum):
    """用户状态枚举"""
    ACTIVE = 0     # 活跃
    INACTIVE = 1   # 禁用


class RouteNotes(IntEnum):
    """路由类型枚举"""
    DEFAULT = 0          # 默认路由
    INTERCONNECT = 1     # 互联地址(/30, /31, /32直连)
    SUBNET = 2           # 子网路由
    NETWORK = 3          # 网络路由
    BLACKHOLE = 4        # 黑洞路由(封禁IP对应此类型)
    GATEWAY = 5          # 网关地址
    NEXTHOP = 6          # 主机路由(下一跳)


class SwitchStatus(IntEnum):
    """交换机角色枚举（前端称 SWITCH_ROLE_MAP）"""
    CORE = 0     # 核心交换机
    ACCESS = 1   # 接入交换机

TOMBSTONE = "__tombstone__"


class SeverityLevel(str, Enum):
    """通知严重级别枚举（字符串值，仅后端使用，不生成前端映射）

    仅包含 notification.severity 字段实际存储的三个级别。
    告警源（CacheAlert / RateLimit）的 severity（low/medium/high/critical）
    由 ops_alert_bridge.SEVERITY_MAP 映射到本枚举后再传入通知链路。
    """
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ChannelType(str, Enum):
    """通知渠道枚举（字符串值，前后端共用，不生成前端映射）

    统一 notification_service / webhook / ops_alert_bridge 中的渠道标识。
    """
    INBOX = "inbox"             # 站内信（个人渠道，始终开启）
    EMAIL = "email"             # 邮件（个人渠道）
    VOICE = "voice"             # 语音通知（个人渠道，默认关闭，需显式开启）
    WECHAT_WORK = "wechat_work"  # 企业微信（广播渠道，群机器人）
    FEISHU = "feishu"           # 飞书（广播渠道，群机器人）
    CUSTOM = "custom"           # 自定义 Webhook（广播渠道）


PERSONAL_CHANNELS = (ChannelType.INBOX, ChannelType.EMAIL)

BROADCAST_CHANNELS = (ChannelType.WECHAT_WORK, ChannelType.FEISHU, ChannelType.CUSTOM)


class DataSource:
    """数据来源标记（仅后端使用，不生成前端映射）"""
    MANUAL = "manual"
    AUTO = "auto"
    HYBRID = "hybrid"


class DeviceStatus:
    """设备状态枚举

    注意：SCRAPPED = 0 表示已报废，不作为软删除标记。
    查询"有效设备"时应过滤 status != DeviceStatus.SCRAPPED。
    Phase 2 扩展：新增 PENDING_ONLINE(6) 和 TESTING(7)。
    """

    SCRAPPED = 0      # 已报废
    AVAILABLE = 1     # 可用（已采购未上架）
    ONLINE = 2        # 在线（已上架运行中）
    OFFLINE = 3       # 离线（已上架但未运行）
    MAINTENANCE = 4   # 维护中
    RESERVED = 5      # 预留（已分配客户但未上架）
    PENDING_ONLINE = 6  # 待上线（已配置等待部署）
    TESTING = 7        # 测试中（测试环境使用）

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
        """检查状态转换是否允许"""
        return to_status in cls.ALLOWED_TRANSITIONS.get(from_status, [])

    @classmethod
    def active_statuses(cls) -> List[int]:
        """返回所有"有效"状态列表（即非报废状态）"""
        return [cls.AVAILABLE, cls.ONLINE, cls.OFFLINE, cls.MAINTENANCE,
                cls.RESERVED, cls.PENDING_ONLINE, cls.TESTING]


class VLANStatus(IntEnum):
    """VLAN 状态枚举（后端编码：1=活跃 0=停用，见 app/models/vlan.py）

    状态 2(预留) 为前端扩展，后端字段仅 0/1。
    """
    INACTIVE = 0   # 停用 / 禁用
    ACTIVE = 1     # 活跃 / 正常
    RESERVED = 2   # 预留（前端扩展）


class LAGStatus(IntEnum):
    """链路聚合(LAG)状态枚举（后端编码：1=活跃 0=停用，见 app/models/link_aggregation.py）

    状态 2(降级) 为前端扩展，后端字段仅 0/1。
    """
    INACTIVE = 0   # 停用 / 禁用
    ACTIVE = 1     # 活跃 / 正常
    DEGRADED = 2   # 降级（前端扩展）


class CustomerStatus(IntEnum):
    """客户状态枚举（见 app/models/customer.py：0-活跃 1-停用 2-待审核 3-终止）"""
    ACTIVE = 0
    DISABLED = 1
    PENDING = 2
    TERMINATED = 3


class RoomStatus(IntEnum):
    """机房状态枚举（见 app/models/room.py：0-正常 1-停用）"""
    NORMAL = 0
    DISABLED = 1


class CabinetStatus(IntEnum):
    """机柜状态枚举（见 app/models/cabinet.py：0-禁用 1-可用 2-使用中 3-维护中 4-已预留）"""
    DISABLED = 0
    AVAILABLE = 1
    IN_USE = 2
    MAINTENANCE = 3
    RESERVED = 4


class NotificationTypeCode(str, Enum):
    """通知类型枚举（字符串值，前后端共用，生成前端映射）

    用于 notification.type 字段、WebhookConfig.applicable_types 过滤、
    用户偏好 subscribed_types 订阅。
    """
    DEVICE_UNREACHABLE = "device_unreachable"
    DEVICE_RECOVERED = "device_recovered"
    TEMPERATURE_ALERT = "temperature_alert"        # 温度超阈值
    DISK_FAILURE_ALERT = "disk_failure_alert"      # 硬盘故障
    PORT_STATUS_CHANGED = "port_status_changed"    # 交换机指定端口 up/down
    MONITOR_INTERRUPTED = "monitor_interrupted"    # 设备监控中断（心跳超时）
    RAID_FAILURE_ALERT = "raid_failure_alert"      # 服务器 RAID 故障
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
    """探测错误码枚举（字符串值，前后端共用，生成前端映射）

    适配器（SNMP/Redfish/IPMI/Zabbix）与 MonitorService 统一使用本枚举
    作为 ProbeResult.error 的规范值。前端据此翻译为中文标签。
    动态异常消息（如 Python traceback 片段）不应作为 error 值，
    应归入 ProbeResult.extra["raw_error"] 供调试。
    """
    TIMEOUT = "timeout"                  # 协议级超时（SNMP 内层协程 / Redfish HTTP / IPMI 请求）
    PROBE_TIMEOUT = "probe_timeout"      # 线程级超时（base_adapter.run_with_timeout 守卫）
    PROBE_ERROR = "probe_error"          # 线程级异常（适配器内部未分类异常）
    NO_MANAGEMENT_IP = "no_management_ip"  # 设备无管理 IP
    DNS_RESOLVE_TIMEOUT = "dns_resolve_timeout"  # DNS 解析超时
    AUTH_FAILED = "auth_failed"          # 认证失败（SNMP community/Redfish token/IPMI 密码错误）
    AUTH_ERROR = "auth_error"            # Redfish HTTP 401 认证失败
    CONNECTION_REFUSED = "connection_refused"  # 连接被拒绝
    CONNECTION_ERROR = "connection_error"  # 连接错误（TCP 层面）
    NETWORK_ERROR = "network_error"      # 网络不可达 / 路由不通
    SSL_ERROR = "ssl_error"              # SSL/TLS 握手失败
    TLS_INCOMPATIBLE = "tls_incompatible"  # TLS 版本/密码套件不兼容（老旧 BMC）
    IPMI_ERROR = "ipmi_error"            # IPMI 协议错误
    IPMI_NO_DATA = "no_data"             # IPMI 返回空数据
    UNKNOWN = "unknown"                  # 未分类错误
    NO_HOST_REF = "no_host_ref"          # Zabbix 凭据无主机引用
    NO_API_URL = "no_api_url"            # Zabbix 无 API URL
    ZABBIX_API_ERROR = "zabbix_api_error"  # Zabbix API 调用失败
    ZABBIX_EMPTY_HOST_LIST = "zabbix_empty_host_list"  # Zabbix 主机列表为空
    HOST_NOT_IN_ZABBIX = "host_not_in_zabbix"  # 主机不在 Zabbix 中



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
    """设备子类型枚举（字符串值，前端对应 DeviceSubtype）

    按 DeviceTypeCode 分组：
    - server: standalone / chassis / node / storage / gpu
    - network: switch / router / firewall
    - other: pdu / ups / other
    """
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
    """交换机驱动类型枚举（字符串值，前端对应 SwitchDeviceType / SWITCH_DEVICE_TYPE_OPTIONS）

    用于 SSH 自动化驱动的厂商识别，adapter_factory 依据此枚举路由适配器。
    """
    HUAWEI = "huawei"
    H3C = "h3c"
    CISCO = "cisco"


class SSHProtocolCode(str, Enum):
    """SSH 连接协议枚举（字符串值，前端对应 SSHProtocol）"""
    SSH = "ssh"
    TELNET = "telnet"


class MonitorProtocolCode(str, Enum):
    """设备监控协议枚举（字符串值，仅后端使用，不生成前端映射）

    各适配器（snmp/ipmi/zabbix/ping）与 MonitorService 统一引用本枚举；
    base_adapter 从本模块导入并透出 MonitorProtocolCode。

    注：Redfish 适配器已停用并归档（见 archive/monitoring/redfish/），
    服务器兜底统一走 IPMI；连通性触发源统一走 PING（复用 ip_status_service）。
    """
    SNMP = "snmp"
    IPMI = "ipmi"
    ZABBIX = "zabbix"  # Zabbix 集中式拉取（作为直连探测的 fallback 源，见 protocol_registry）
    PING = "ping"  # 连通性触发源（复用 ip_status_service 的 ping + TCP 端口探测）


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
