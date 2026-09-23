
export enum IPStatusCode {
  ACTIVE = 0,
  INACTIVE = 1,
  BANNED = 2,
  UNUSED = 3,
  PENDING_BAN = 4,
  PENDING_UNBAN = 5,
}

export type IPStatusKey =
  'ipStatus.ACTIVE' |
  'ipStatus.INACTIVE' |
  'ipStatus.BANNED' |
  'ipStatus.UNUSED' |
  'ipStatus.PENDING_BAN' |
  'ipStatus.PENDING_UNBAN';

export const IP_STATUS_MAP: Record<IPStatusCode, { labelKey: IPStatusKey; color: string }> = {
  [IPStatusCode.ACTIVE]: { labelKey: 'ipStatus.ACTIVE', color: 'green' },
  [IPStatusCode.INACTIVE]: { labelKey: 'ipStatus.INACTIVE', color: 'default' },
  [IPStatusCode.BANNED]: { labelKey: 'ipStatus.BANNED', color: 'red' },
  [IPStatusCode.UNUSED]: { labelKey: 'ipStatus.UNUSED', color: 'blue' },
  [IPStatusCode.PENDING_BAN]: { labelKey: 'ipStatus.PENDING_BAN', color: 'orange' },
  [IPStatusCode.PENDING_UNBAN]: { labelKey: 'ipStatus.PENDING_UNBAN', color: 'orange' },
};

export enum RouteNotesCode {
  DEFAULT = 0,
  INTERCONNECT = 1,
  SUBNET = 2,
  NETWORK = 3,
  BLACKHOLE = 4,
  GATEWAY = 5,
  NEXTHOP = 6,
}

export type RouteNoteKey =
  'routeNote.DEFAULT' |
  'routeNote.INTERCONNECT' |
  'routeNote.SUBNET' |
  'routeNote.NETWORK' |
  'routeNote.BLACKHOLE' |
  'routeNote.GATEWAY' |
  'routeNote.NEXTHOP';

export const ROUTE_NOTES_MAP: Record<number, { labelKey: RouteNoteKey; color: string }> = {
  [RouteNotesCode.DEFAULT]: { labelKey: 'routeNote.DEFAULT', color: 'default' },
  [RouteNotesCode.INTERCONNECT]: { labelKey: 'routeNote.INTERCONNECT', color: 'blue' },
  [RouteNotesCode.SUBNET]: { labelKey: 'routeNote.SUBNET', color: 'green' },
  [RouteNotesCode.NETWORK]: { labelKey: 'routeNote.NETWORK', color: 'cyan' },
  [RouteNotesCode.BLACKHOLE]: { labelKey: 'routeNote.BLACKHOLE', color: 'red' },
  [RouteNotesCode.GATEWAY]: { labelKey: 'routeNote.GATEWAY', color: 'purple' },
  [RouteNotesCode.NEXTHOP]: { labelKey: 'routeNote.NEXTHOP', color: 'orange' },
};

export enum SwitchRoleCode {
  CORE = 0,
  ACCESS = 1,
}

export type SwitchRoleKey = 'switchRole.CORE' | 'switchRole.ACCESS';

export const SWITCH_ROLE_MAP: Record<SwitchRoleCode, { labelKey: SwitchRoleKey; color: string }> = {
  [SwitchRoleCode.CORE]: { labelKey: 'switchRole.CORE', color: 'blue' },
  [SwitchRoleCode.ACCESS]: { labelKey: 'switchRole.ACCESS', color: 'green' },
};

export enum DeviceStatusCode {
  SCRAPPED = 0,
  AVAILABLE = 1,
  ONLINE = 2,
  OFFLINE = 3,
  MAINTENANCE = 4,
  RESERVED = 5,
  PENDING_ONLINE = 6,
  TESTING = 7,
}

export type DeviceStatusKey =
  'status.SCRAPPED' |
  'status.AVAILABLE' |
  'status.ONLINE' |
  'status.OFFLINE' |
  'status.MAINTENANCE' |
  'status.RESERVED' |
  'status.PENDING_ONLINE' |
  'status.TESTING';

export const DEVICE_STATUS_MAP: Record<DeviceStatusCode, { labelKey: DeviceStatusKey; color: string }> = {
  [DeviceStatusCode.SCRAPPED]: { labelKey: 'status.SCRAPPED', color: 'default' },
  [DeviceStatusCode.AVAILABLE]: { labelKey: 'status.AVAILABLE', color: 'blue' },
  [DeviceStatusCode.ONLINE]: { labelKey: 'status.ONLINE', color: 'green' },
  [DeviceStatusCode.OFFLINE]: { labelKey: 'status.OFFLINE', color: 'red' },
  [DeviceStatusCode.MAINTENANCE]: { labelKey: 'status.MAINTENANCE', color: 'orange' },
  [DeviceStatusCode.RESERVED]: { labelKey: 'status.RESERVED', color: 'purple' },
  [DeviceStatusCode.PENDING_ONLINE]: { labelKey: 'status.PENDING_ONLINE', color: 'cyan' },
  [DeviceStatusCode.TESTING]: { labelKey: 'status.TESTING', color: 'geekblue' },
};

export enum CustomerStatusCode {
  ACTIVE = 0,
  DISABLED = 1,
  PENDING = 2,
  TERMINATED = 3,
}

export type CustomerStatusKey =
  'customerStatus.ACTIVE' |
  'customerStatus.DISABLED' |
  'customerStatus.PENDING' |
  'customerStatus.TERMINATED';

export const CUSTOMER_STATUS_MAP: Record<CustomerStatusCode, { labelKey: CustomerStatusKey; color: string }> = {
  [CustomerStatusCode.ACTIVE]: { labelKey: 'customerStatus.ACTIVE', color: 'green' },
  [CustomerStatusCode.DISABLED]: { labelKey: 'customerStatus.DISABLED', color: 'red' },
  [CustomerStatusCode.PENDING]: { labelKey: 'customerStatus.PENDING', color: 'orange' },
  [CustomerStatusCode.TERMINATED]: { labelKey: 'customerStatus.TERMINATED', color: 'default' },
};

export enum RoomStatusCode {
  NORMAL = 0,
  DISABLED = 1,
}

export type RoomStatusKey = 'roomStatus.NORMAL' | 'roomStatus.DISABLED';

export const ROOM_STATUS_MAP: Record<RoomStatusCode, { labelKey: RoomStatusKey; color: string }> = {
  [RoomStatusCode.NORMAL]: { labelKey: 'roomStatus.NORMAL', color: 'green' },
  [RoomStatusCode.DISABLED]: { labelKey: 'roomStatus.DISABLED', color: 'red' },
};

export enum CabinetStatusCode {
  DISABLED = 0,
  AVAILABLE = 1,
  IN_USE = 2,
  MAINTENANCE = 3,
  RESERVED = 4,
}

export type CabinetStatusKey =
  'cabinetStatus.DISABLED' |
  'cabinetStatus.AVAILABLE' |
  'cabinetStatus.IN_USE' |
  'cabinetStatus.MAINTENANCE' |
  'cabinetStatus.RESERVED';

export const CABINET_STATUS_MAP: Record<CabinetStatusCode, { labelKey: CabinetStatusKey; color: string }> = {
  [CabinetStatusCode.DISABLED]: { labelKey: 'cabinetStatus.DISABLED', color: 'red' },
  [CabinetStatusCode.AVAILABLE]: { labelKey: 'cabinetStatus.AVAILABLE', color: 'green' },
  [CabinetStatusCode.IN_USE]: { labelKey: 'cabinetStatus.IN_USE', color: 'blue' },
  [CabinetStatusCode.MAINTENANCE]: { labelKey: 'cabinetStatus.MAINTENANCE', color: 'orange' },
  [CabinetStatusCode.RESERVED]: { labelKey: 'cabinetStatus.RESERVED', color: 'purple' },
};

export enum VLANStatusCode {
  INACTIVE = 0,
  ACTIVE = 1,
  RESERVED = 2,
}

export type VLANStatusKey =
  'vlanStatus.INACTIVE' |
  'vlanStatus.ACTIVE' |
  'vlanStatus.RESERVED';

export const VLAN_STATUS_MAP: Record<number, { labelKey: VLANStatusKey; color: string }> = {
  [VLANStatusCode.INACTIVE]: { labelKey: 'vlanStatus.INACTIVE', color: 'red' },
  [VLANStatusCode.ACTIVE]: { labelKey: 'vlanStatus.ACTIVE', color: 'green' },
  [VLANStatusCode.RESERVED]: { labelKey: 'vlanStatus.RESERVED', color: 'orange' },
};

export enum UserStatusCode {
  ACTIVE = 0,
  INACTIVE = 1,
}

export type UserStatusKey = 'userStatus.ACTIVE' | 'userStatus.INACTIVE';

export const USER_STATUS_MAP: Record<UserStatusCode, { labelKey: UserStatusKey; color: string }> = {
  [UserStatusCode.ACTIVE]: { labelKey: 'userStatus.ACTIVE', color: 'green' },
  [UserStatusCode.INACTIVE]: { labelKey: 'userStatus.INACTIVE', color: 'red' },
};

export enum LAGStatusCode {
  INACTIVE = 0,
  ACTIVE = 1,
  DEGRADED = 2,
}

export type LAGStatusKey =
  'lagStatus.INACTIVE' |
  'lagStatus.ACTIVE' |
  'lagStatus.DEGRADED';

export const LAG_STATUS_MAP: Record<number, { labelKey: LAGStatusKey; color: string }> = {
  [LAGStatusCode.INACTIVE]: { labelKey: 'lagStatus.INACTIVE', color: 'red' },
  [LAGStatusCode.ACTIVE]: { labelKey: 'lagStatus.ACTIVE', color: 'green' },
  [LAGStatusCode.DEGRADED]: { labelKey: 'lagStatus.DEGRADED', color: 'orange' },
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
  RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded',
  SERVICE_UNHEALTHY = 'service_unhealthy',
  SERVICE_RECOVERED = 'service_recovered',
  ASSET_WARRANTY_ALERT = 'asset_warranty_alert',
}

export type NotificationTypeKey =
  'notificationType.DEVICE_UNREACHABLE' |
  'notificationType.DEVICE_RECOVERED' |
  'notificationType.TEMPERATURE_ALERT' |
  'notificationType.DISK_FAILURE_ALERT' |
  'notificationType.PORT_STATUS_CHANGED' |
  'notificationType.MONITOR_INTERRUPTED' |
  'notificationType.RAID_FAILURE_ALERT' |
  'notificationType.BATCH_CREATE_DEVICES' |
  'notificationType.BATCH_BAN_IP' |
  'notificationType.BATCH_UNBAN_IP' |
  'notificationType.IP_SCAN_COMPLETE' |
  'notificationType.IP_SCAN_FAILED' |
  'notificationType.ROOM_SCAN_COMPLETE' |
  'notificationType.ROOM_SCAN_FAILED' |
  'notificationType.VIRTUAL_ROOM_SCAN_COMPLETE' |
  'notificationType.VIRTUAL_ROOM_SCAN_FAILED' |
  'notificationType.PORT_ACTION' |
  'notificationType.ASYNC_ACTION' |
  'notificationType.RATE_LIMIT_EXCEEDED' |
  'notificationType.SERVICE_UNHEALTHY' |
  'notificationType.SERVICE_RECOVERED' |
  'notificationType.ASSET_WARRANTY_ALERT';

export const NOTIFICATION_TYPE_LABEL_KEYS: Record<NotificationTypeCode, NotificationTypeKey> = {
  [NotificationTypeCode.DEVICE_UNREACHABLE]: 'notificationType.DEVICE_UNREACHABLE',
  [NotificationTypeCode.DEVICE_RECOVERED]: 'notificationType.DEVICE_RECOVERED',
  [NotificationTypeCode.TEMPERATURE_ALERT]: 'notificationType.TEMPERATURE_ALERT',
  [NotificationTypeCode.DISK_FAILURE_ALERT]: 'notificationType.DISK_FAILURE_ALERT',
  [NotificationTypeCode.PORT_STATUS_CHANGED]: 'notificationType.PORT_STATUS_CHANGED',
  [NotificationTypeCode.MONITOR_INTERRUPTED]: 'notificationType.MONITOR_INTERRUPTED',
  [NotificationTypeCode.RAID_FAILURE_ALERT]: 'notificationType.RAID_FAILURE_ALERT',
  [NotificationTypeCode.BATCH_CREATE_DEVICES]: 'notificationType.BATCH_CREATE_DEVICES',
  [NotificationTypeCode.BATCH_BAN_IP]: 'notificationType.BATCH_BAN_IP',
  [NotificationTypeCode.BATCH_UNBAN_IP]: 'notificationType.BATCH_UNBAN_IP',
  [NotificationTypeCode.IP_SCAN_COMPLETE]: 'notificationType.IP_SCAN_COMPLETE',
  [NotificationTypeCode.IP_SCAN_FAILED]: 'notificationType.IP_SCAN_FAILED',
  [NotificationTypeCode.ROOM_SCAN_COMPLETE]: 'notificationType.ROOM_SCAN_COMPLETE',
  [NotificationTypeCode.ROOM_SCAN_FAILED]: 'notificationType.ROOM_SCAN_FAILED',
  [NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE]: 'notificationType.VIRTUAL_ROOM_SCAN_COMPLETE',
  [NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED]: 'notificationType.VIRTUAL_ROOM_SCAN_FAILED',
  [NotificationTypeCode.PORT_ACTION]: 'notificationType.PORT_ACTION',
  [NotificationTypeCode.ASYNC_ACTION]: 'notificationType.ASYNC_ACTION',
  [NotificationTypeCode.RATE_LIMIT_EXCEEDED]: 'notificationType.RATE_LIMIT_EXCEEDED',
  [NotificationTypeCode.SERVICE_UNHEALTHY]: 'notificationType.SERVICE_UNHEALTHY',
  [NotificationTypeCode.SERVICE_RECOVERED]: 'notificationType.SERVICE_RECOVERED',
  [NotificationTypeCode.ASSET_WARRANTY_ALERT]: 'notificationType.ASSET_WARRANTY_ALERT',
};

export type NotificationGroupKey = 'notificationGroup.MONITOR' | 'notificationGroup.OPERATION' | 'notificationGroup.SCAN' | 'notificationGroup.PORT_ASYNC' | 'notificationGroup.OPS' | 'notificationGroup.ASSET';

export const NOTIFICATION_TYPE_GROUPS: {
  groupKey: NotificationGroupKey;
  types: NotificationTypeCode[];
}[] = [
  {
    groupKey: 'notificationGroup.MONITOR',
    types: [
      NotificationTypeCode.DEVICE_UNREACHABLE,
      NotificationTypeCode.DEVICE_RECOVERED,
      NotificationTypeCode.TEMPERATURE_ALERT,
      NotificationTypeCode.DISK_FAILURE_ALERT,
      NotificationTypeCode.PORT_STATUS_CHANGED,
      NotificationTypeCode.MONITOR_INTERRUPTED,
      NotificationTypeCode.RAID_FAILURE_ALERT,
    ],
  },
  {
    groupKey: 'notificationGroup.OPERATION',
    types: [
      NotificationTypeCode.BATCH_CREATE_DEVICES,
      NotificationTypeCode.BATCH_BAN_IP,
      NotificationTypeCode.BATCH_UNBAN_IP,
    ],
  },
  {
    groupKey: 'notificationGroup.SCAN',
    types: [
      NotificationTypeCode.IP_SCAN_COMPLETE,
      NotificationTypeCode.IP_SCAN_FAILED,
      NotificationTypeCode.ROOM_SCAN_COMPLETE,
      NotificationTypeCode.ROOM_SCAN_FAILED,
      NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE,
      NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED,
    ],
  },
  {
    groupKey: 'notificationGroup.PORT_ASYNC',
    types: [
      NotificationTypeCode.PORT_ACTION,
      NotificationTypeCode.ASYNC_ACTION,
    ],
  },
  {
    groupKey: 'notificationGroup.OPS',
    types: [
      NotificationTypeCode.RATE_LIMIT_EXCEEDED,
      NotificationTypeCode.SERVICE_UNHEALTHY,
      NotificationTypeCode.SERVICE_RECOVERED,
    ],
  },
  {
    groupKey: 'notificationGroup.ASSET',
    types: [
      NotificationTypeCode.ASSET_WARRANTY_ALERT,
    ],
  },
];

export enum ProbeErrorCode {
  TIMEOUT = 'timeout',
  PROBE_TIMEOUT = 'probe_timeout',
  PROBE_ERROR = 'probe_error',
  NO_MANAGEMENT_IP = 'no_management_ip',
  INVALID_TARGET_IP = 'invalid_target_ip',
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
  HOST_NOT_IN_ZABBIX = 'host_not_in_zabbix',
}

export type ProbeErrorKey =
  'probeError.TIMEOUT' |
  'probeError.PROBE_TIMEOUT' |
  'probeError.PROBE_ERROR' |
  'probeError.NO_MANAGEMENT_IP' |
  'probeError.INVALID_TARGET_IP' |
  'probeError.DNS_RESOLVE_TIMEOUT' |
  'probeError.AUTH_FAILED' |
  'probeError.AUTH_ERROR' |
  'probeError.CONNECTION_REFUSED' |
  'probeError.CONNECTION_ERROR' |
  'probeError.NETWORK_ERROR' |
  'probeError.SSL_ERROR' |
  'probeError.TLS_INCOMPATIBLE' |
  'probeError.IPMI_ERROR' |
  'probeError.IPMI_NO_DATA' |
  'probeError.UNKNOWN' |
  'probeError.NO_HOST_REF' |
  'probeError.NO_API_URL' |
  'probeError.ZABBIX_API_ERROR' |
  'probeError.ZABBIX_EMPTY_HOST_LIST' |
  'probeError.HOST_NOT_IN_ZABBIX';

export const PROBE_ERROR_MAP: Record<ProbeErrorCode, { labelKey: ProbeErrorKey; color: string }> = {
  [ProbeErrorCode.TIMEOUT]: { labelKey: 'probeError.TIMEOUT', color: 'orange' },
  [ProbeErrorCode.PROBE_TIMEOUT]: { labelKey: 'probeError.PROBE_TIMEOUT', color: 'red' },
  [ProbeErrorCode.PROBE_ERROR]: { labelKey: 'probeError.PROBE_ERROR', color: 'red' },
  [ProbeErrorCode.NO_MANAGEMENT_IP]: { labelKey: 'probeError.NO_MANAGEMENT_IP', color: 'default' },
  [ProbeErrorCode.INVALID_TARGET_IP]: { labelKey: 'probeError.INVALID_TARGET_IP', color: 'red' },
  [ProbeErrorCode.DNS_RESOLVE_TIMEOUT]: { labelKey: 'probeError.DNS_RESOLVE_TIMEOUT', color: 'orange' },
  [ProbeErrorCode.AUTH_FAILED]: { labelKey: 'probeError.AUTH_FAILED', color: 'red' },
  [ProbeErrorCode.AUTH_ERROR]: { labelKey: 'probeError.AUTH_ERROR', color: 'red' },
  [ProbeErrorCode.CONNECTION_REFUSED]: { labelKey: 'probeError.CONNECTION_REFUSED', color: 'red' },
  [ProbeErrorCode.CONNECTION_ERROR]: { labelKey: 'probeError.CONNECTION_ERROR', color: 'red' },
  [ProbeErrorCode.NETWORK_ERROR]: { labelKey: 'probeError.NETWORK_ERROR', color: 'red' },
  [ProbeErrorCode.SSL_ERROR]: { labelKey: 'probeError.SSL_ERROR', color: 'red' },
  [ProbeErrorCode.TLS_INCOMPATIBLE]: { labelKey: 'probeError.TLS_INCOMPATIBLE', color: 'red' },
  [ProbeErrorCode.IPMI_ERROR]: { labelKey: 'probeError.IPMI_ERROR', color: 'red' },
  [ProbeErrorCode.IPMI_NO_DATA]: { labelKey: 'probeError.IPMI_NO_DATA', color: 'orange' },
  [ProbeErrorCode.UNKNOWN]: { labelKey: 'probeError.UNKNOWN', color: 'default' },
  [ProbeErrorCode.NO_HOST_REF]: { labelKey: 'probeError.NO_HOST_REF', color: 'default' },
  [ProbeErrorCode.NO_API_URL]: { labelKey: 'probeError.NO_API_URL', color: 'default' },
  [ProbeErrorCode.ZABBIX_API_ERROR]: { labelKey: 'probeError.ZABBIX_API_ERROR', color: 'red' },
  [ProbeErrorCode.ZABBIX_EMPTY_HOST_LIST]: { labelKey: 'probeError.ZABBIX_EMPTY_HOST_LIST', color: 'orange' },
  [ProbeErrorCode.HOST_NOT_IN_ZABBIX]: { labelKey: 'probeError.HOST_NOT_IN_ZABBIX', color: 'orange' },
};

export enum IPAuditAction {
  ALLOCATE = 'allocate',
  RELEASE = 'release',
  BAN = 'ban',
  UNBAN = 'unban',
}

export type IPAuditActionKey =
  'ipAuditAction.ALLOCATE' |
  'ipAuditAction.RELEASE' |
  'ipAuditAction.BAN' |
  'ipAuditAction.UNBAN';

export const IP_AUDIT_ACTION_MAP: Record<IPAuditAction, { labelKey: IPAuditActionKey; color: string }> = {
  [IPAuditAction.ALLOCATE]: { labelKey: 'ipAuditAction.ALLOCATE', color: 'green' },
  [IPAuditAction.RELEASE]: { labelKey: 'ipAuditAction.RELEASE', color: 'orange' },
  [IPAuditAction.BAN]: { labelKey: 'ipAuditAction.BAN', color: 'red' },
  [IPAuditAction.UNBAN]: { labelKey: 'ipAuditAction.UNBAN', color: 'blue' },
};

export enum SwitchDeviceType {
  HUAWEI = 'huawei',
  H3C = 'h3c',
  CISCO = 'cisco',
}

export type SwitchDeviceTypeKey =
  'switchDeviceType.HUAWEI' |
  'switchDeviceType.H3C' |
  'switchDeviceType.CISCO';

export const SWITCH_DEVICE_TYPE_LABEL_KEYS: Record<SwitchDeviceType, SwitchDeviceTypeKey> = {
  [SwitchDeviceType.HUAWEI]: 'switchDeviceType.HUAWEI',
  [SwitchDeviceType.H3C]: 'switchDeviceType.H3C',
  [SwitchDeviceType.CISCO]: 'switchDeviceType.CISCO',
};

export enum SSHProtocol {
  SSH = 'ssh',
  TELNET = 'telnet',
}

export const SSH_PROTOCOL_OPTIONS = [
  { label: 'SSH', value: 'ssh' },
  { label: 'Telnet', value: 'telnet' },
];

