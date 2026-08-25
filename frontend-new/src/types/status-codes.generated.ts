

export enum IPStatusCode {
  ACTIVE = 0,
  INACTIVE = 1,
  BANNED = 2,
  UNUSED = 3,
  PENDING_BAN = 4,
  PENDING_UNBAN = 5
}

export const IP_STATUS_MAP: Record<IPStatusCode, { label: string; color: string }> = {
  [IPStatusCode.ACTIVE]: { label: '活跃', color: 'green' },
  [IPStatusCode.INACTIVE]: { label: '非活跃', color: 'default' },
  [IPStatusCode.BANNED]: { label: '封禁', color: 'red' },
  [IPStatusCode.UNUSED]: { label: '未使用', color: 'blue' },
  [IPStatusCode.PENDING_BAN]: { label: '封禁中', color: 'orange' },
  [IPStatusCode.PENDING_UNBAN]: { label: '解封中', color: 'orange' }
};

export const IP_STATUS_OPTIONS = Object.entries(IP_STATUS_MAP).map(([value, { label }]) => ({
  value: Number(value),
  label
}));

export enum RouteNotesCode {
  DEFAULT = 0,
  INTERCONNECT = 1,
  SUBNET = 2,
  NETWORK = 3,
  BLACKHOLE = 4,
  GATEWAY = 5,
  NEXTHOP = 6
}

export const ROUTE_NOTES_MAP: Record<number, { label: string; color: string }> = {
  [RouteNotesCode.DEFAULT]: { label: '默认路由', color: 'default' },
  [RouteNotesCode.INTERCONNECT]: { label: '互联地址', color: 'blue' },
  [RouteNotesCode.SUBNET]: { label: '子网路由', color: 'green' },
  [RouteNotesCode.NETWORK]: { label: '网络路由', color: 'cyan' },
  [RouteNotesCode.BLACKHOLE]: { label: '黑洞路由', color: 'red' },
  [RouteNotesCode.GATEWAY]: { label: '网关地址', color: 'purple' },
  [RouteNotesCode.NEXTHOP]: { label: '下一跳地址', color: 'orange' }
};

export enum SwitchRoleCode {
  CORE = 0,
  ACCESS = 1
}

export const SWITCH_ROLE_MAP: Record<SwitchRoleCode, { label: string; color: string }> = {
  [SwitchRoleCode.CORE]: { label: '核心交换机', color: 'blue' },
  [SwitchRoleCode.ACCESS]: { label: '接入交换机', color: 'green' }
};

export enum DeviceStatusCode {
  SCRAPPED = 0,
  AVAILABLE = 1,
  ONLINE = 2,
  OFFLINE = 3,
  MAINTENANCE = 4,
  RESERVED = 5,
  PENDING_ONLINE = 6,
  TESTING = 7
}

export const DEVICE_STATUS_MAP: Record<DeviceStatusCode, { label: string; color: string }> = {
  [DeviceStatusCode.SCRAPPED]: { label: '已报废', color: 'default' },
  [DeviceStatusCode.AVAILABLE]: { label: '可用', color: 'blue' },
  [DeviceStatusCode.ONLINE]: { label: '在线', color: 'green' },
  [DeviceStatusCode.OFFLINE]: { label: '离线', color: 'red' },
  [DeviceStatusCode.MAINTENANCE]: { label: '维护中', color: 'orange' },
  [DeviceStatusCode.RESERVED]: { label: '预留', color: 'purple' },
  [DeviceStatusCode.PENDING_ONLINE]: { label: '待上线', color: 'cyan' },
  [DeviceStatusCode.TESTING]: { label: '测试中', color: 'geekblue' }
};

export const DEVICE_STATUS_OPTIONS = Object.entries(DEVICE_STATUS_MAP).map(
  ([value, { label }]) => ({ value: Number(value), label })
);

export enum CustomerStatusCode {
  ACTIVE = 0,
  DISABLED = 1,
  PENDING = 2,
  TERMINATED = 3
}

export const CUSTOMER_STATUS_MAP: Record<CustomerStatusCode, { label: string; color: string }> = {
  [CustomerStatusCode.ACTIVE]: { label: '活跃', color: 'green' },
  [CustomerStatusCode.DISABLED]: { label: '停用', color: 'red' },
  [CustomerStatusCode.PENDING]: { label: '待审核', color: 'orange' },
  [CustomerStatusCode.TERMINATED]: { label: '终止', color: 'default' }
};

export const CUSTOMER_STATUS_OPTIONS = Object.entries(CUSTOMER_STATUS_MAP).map(
  ([value, { label }]) => ({ value: Number(value), label })
);

export enum RoomStatusCode {
  NORMAL = 0,
  DISABLED = 1
}

export const ROOM_STATUS_MAP: Record<RoomStatusCode, { label: string; color: string }> = {
  [RoomStatusCode.NORMAL]: { label: '正常', color: 'green' },
  [RoomStatusCode.DISABLED]: { label: '停用', color: 'red' }
};

export const ROOM_STATUS_OPTIONS = Object.entries(ROOM_STATUS_MAP).map(([value, { label }]) => ({
  value: Number(value),
  label
}));

export enum CabinetStatusCode {
  DISABLED = 0,
  AVAILABLE = 1,
  IN_USE = 2,
  MAINTENANCE = 3,
  RESERVED = 4
}

export const CABINET_STATUS_MAP: Record<CabinetStatusCode, { label: string; color: string }> = {
  [CabinetStatusCode.DISABLED]: { label: '禁用', color: 'red' },
  [CabinetStatusCode.AVAILABLE]: { label: '可用', color: 'green' },
  [CabinetStatusCode.IN_USE]: { label: '使用中', color: 'blue' },
  [CabinetStatusCode.MAINTENANCE]: { label: '维护中', color: 'orange' },
  [CabinetStatusCode.RESERVED]: { label: '已预留', color: 'purple' }
};

export const CABINET_STATUS_OPTIONS = Object.entries(CABINET_STATUS_MAP).map(
  ([value, { label }]) => ({ value: Number(value), label })
);

export enum VLANStatusCode {
  INACTIVE = 0,
  ACTIVE = 1,
  RESERVED = 2
}

export const VLAN_STATUS_MAP: Record<number, { label: string; color: string }> = {
  [VLANStatusCode.INACTIVE]: { label: '禁用', color: 'red' },
  [VLANStatusCode.ACTIVE]: { label: '正常', color: 'green' },
  [VLANStatusCode.RESERVED]: { label: '预留', color: 'orange' }
};

export enum UserStatusCode {
  ACTIVE = 0,
  INACTIVE = 1
}

export const USER_STATUS_MAP: Record<UserStatusCode, { label: string; color: string }> = {
  [UserStatusCode.ACTIVE]: { label: '活跃', color: 'green' },
  [UserStatusCode.INACTIVE]: { label: '禁用', color: 'red' }
};

export const USER_STATUS_OPTIONS = Object.entries(USER_STATUS_MAP).map(([value, { label }]) => ({
  value: Number(value),
  label
}));

export enum LAGStatusCode {
  INACTIVE = 0,
  ACTIVE = 1,
  DEGRADED = 2
}

export const LAG_STATUS_MAP: Record<number, { label: string; color: string }> = {
  [LAGStatusCode.INACTIVE]: { label: '禁用', color: 'red' },
  [LAGStatusCode.ACTIVE]: { label: '正常', color: 'green' },
  [LAGStatusCode.DEGRADED]: { label: '降级', color: 'orange' }
};

export enum NotificationTypeCode {
  DEVICE_UNREACHABLE = 'device_unreachable',
  DEVICE_RECOVERED = 'device_recovered',
  TEMPERATURE_ALERT = 'temperature_alert',
  DISK_FAILURE_ALERT = 'disk_failure_alert',
  PORT_STATUS_CHANGED = 'port_status_changed',
  MONITOR_INTERRUPTED = 'monitor_interrupted',
  RAID_FAILURE_ALERT = 'raid_failure_alert',
  BATCH_CREATE_DEVICES = 'batch_create_devices',
  BATCH_BAN_IP = 'batch_ban_ip',
  BATCH_UNBAN_IP = 'batch_unban_ip',
  IP_SCAN_COMPLETE = 'ip_scan_complete',
  IP_SCAN_FAILED = 'ip_scan_failed',
  ROOM_SCAN_COMPLETE = 'room_scan_complete',
  ROOM_SCAN_FAILED = 'room_scan_failed',
  VIRTUAL_ROOM_SCAN_COMPLETE = 'virtual_room_scan_complete',
  VIRTUAL_ROOM_SCAN_FAILED = 'virtual_room_scan_failed',
  PORT_ACTION = 'port_action',
  ASYNC_ACTION = 'async_action',
  RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'
}

export const NOTIFICATION_TYPE_OPTIONS = [
  { label: '设备不可达', value: 'device_unreachable' },
  { label: '设备恢复', value: 'device_recovered' },
  { label: '温度告警', value: 'temperature_alert' },
  { label: '硬盘故障', value: 'disk_failure_alert' },
  { label: '端口状态变化', value: 'port_status_changed' },
  { label: '监控中断', value: 'monitor_interrupted' },
  { label: 'RAID故障', value: 'raid_failure_alert' },
  { label: '批量创建设备', value: 'batch_create_devices' },
  { label: '批量封禁IP', value: 'batch_ban_ip' },
  { label: '批量解封IP', value: 'batch_unban_ip' },
  { label: 'IP扫描完成', value: 'ip_scan_complete' },
  { label: 'IP扫描失败', value: 'ip_scan_failed' },
  { label: '机房扫描完成', value: 'room_scan_complete' },
  { label: '机房扫描失败', value: 'room_scan_failed' },
  { label: '虚拟机房扫描完成', value: 'virtual_room_scan_complete' },
  { label: '虚拟机房扫描失败', value: 'virtual_room_scan_failed' },
  { label: '端口操作结果', value: 'port_action' },
  { label: '异步操作结果', value: 'async_action' },
  { label: '频率超限', value: 'rate_limit_exceeded' }
];

export enum ProbeErrorCode {
  TIMEOUT = 'timeout',
  PROBE_TIMEOUT = 'probe_timeout',
  PROBE_ERROR = 'probe_error',
  NO_MANAGEMENT_IP = 'no_management_ip',
  DNS_RESOLVE_TIMEOUT = 'dns_resolve_timeout',
  AUTH_FAILED = 'auth_failed',
  AUTH_ERROR = 'auth_error',
  CONNECTION_REFUSED = 'connection_refused',
  CONNECTION_ERROR = 'connection_error',
  NETWORK_ERROR = 'network_error',
  SSL_ERROR = 'ssl_error',
  TLS_INCOMPATIBLE = 'tls_incompatible',
  IPMI_ERROR = 'ipmi_error',
  IPMI_NO_DATA = 'no_data',
  UNKNOWN = 'unknown',
  NO_HOST_REF = 'no_host_ref',
  NO_API_URL = 'no_api_url',
  ZABBIX_API_ERROR = 'zabbix_api_error',
  ZABBIX_EMPTY_HOST_LIST = 'zabbix_empty_host_list',
  HOST_NOT_IN_ZABBIX = 'host_not_in_zabbix'
}

export const PROBE_ERROR_MAP: Record<ProbeErrorCode, { label: string; color: string }> = {
  [ProbeErrorCode.TIMEOUT]: { label: '超时', color: 'orange' },
  [ProbeErrorCode.PROBE_TIMEOUT]: { label: '探测超时', color: 'red' },
  [ProbeErrorCode.PROBE_ERROR]: { label: '探测异常', color: 'red' },
  [ProbeErrorCode.NO_MANAGEMENT_IP]: { label: '无管理IP', color: 'default' },
  [ProbeErrorCode.DNS_RESOLVE_TIMEOUT]: { label: 'DNS解析超时', color: 'orange' },
  [ProbeErrorCode.AUTH_FAILED]: { label: '认证失败', color: 'red' },
  [ProbeErrorCode.AUTH_ERROR]: { label: '认证失败', color: 'red' },
  [ProbeErrorCode.CONNECTION_REFUSED]: { label: '连接被拒绝', color: 'red' },
  [ProbeErrorCode.CONNECTION_ERROR]: { label: '连接错误', color: 'red' },
  [ProbeErrorCode.NETWORK_ERROR]: { label: '网络错误', color: 'red' },
  [ProbeErrorCode.SSL_ERROR]: { label: 'SSL错误', color: 'red' },
  [ProbeErrorCode.TLS_INCOMPATIBLE]: { label: 'TLS不兼容', color: 'red' },
  [ProbeErrorCode.IPMI_ERROR]: { label: 'IPMI错误', color: 'red' },
  [ProbeErrorCode.IPMI_NO_DATA]: { label: 'IPMI无数据', color: 'orange' },
  [ProbeErrorCode.UNKNOWN]: { label: '未知错误', color: 'default' },
  [ProbeErrorCode.NO_HOST_REF]: { label: '无主机引用', color: 'default' },
  [ProbeErrorCode.NO_API_URL]: { label: '无API地址', color: 'default' },
  [ProbeErrorCode.ZABBIX_API_ERROR]: { label: 'Zabbix API错误', color: 'red' },
  [ProbeErrorCode.ZABBIX_EMPTY_HOST_LIST]: { label: 'Zabbix主机列表为空', color: 'orange' },
  [ProbeErrorCode.HOST_NOT_IN_ZABBIX]: { label: '主机不在Zabbix中', color: 'orange' }
};


export const NOTIFICATION_TYPE_GROUP_OPTIONS = [
  {
    label: '监控告警',
    options: [
      { value: 'device_unreachable', label: '设备不可达' },
      { value: 'device_recovered', label: '设备恢复' },
      { value: 'temperature_alert', label: 'temperature_alert' },
      { value: 'disk_failure_alert', label: 'disk_failure_alert' },
      { value: 'port_status_changed', label: 'port_status_changed' },
      { value: 'monitor_interrupted', label: 'monitor_interrupted' },
      { value: 'raid_failure_alert', label: 'raid_failure_alert' }
    ]
  },
  {
    label: '操作结果',
    options: [
      { value: 'batch_create_devices', label: '批量创建设备' },
      { value: 'batch_ban_ip', label: '批量封禁IP' },
      { value: 'batch_unban_ip', label: '批量解封IP' }
    ]
  },
  {
    label: '扫描完成',
    options: [
      { value: 'ip_scan_complete', label: 'IP扫描完成' },
      { value: 'ip_scan_failed', label: 'IP扫描失败' },
      { value: 'room_scan_complete', label: '机房扫描完成' },
      { value: 'room_scan_failed', label: '机房扫描失败' },
      { value: 'virtual_room_scan_complete', label: '虚拟机房扫描完成' },
      { value: 'virtual_room_scan_failed', label: '虚拟机房扫描失败' }
    ]
  },
  {
    label: '端口/异步操作',
    options: [
      { value: 'port_action', label: '端口操作结果' },
      { value: 'async_action', label: '异步操作结果' }
    ]
  },
  {
    label: '运维告警',
    options: [{ value: 'rate_limit_exceeded', label: '频率超限' }]
  }
];
