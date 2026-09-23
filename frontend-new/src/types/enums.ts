
export * from './status-codes.generated';


export enum DeviceType {
  SERVER = 'server',
  NETWORK = 'network',
  OTHER = 'other'
}

export type DeviceTypeKey = 'deviceType.SERVER' | 'deviceType.NETWORK' | 'deviceType.OTHER';

export const DEVICE_TYPE_MAP: Record<DeviceType, { labelKey: DeviceTypeKey; color: string }> = {
  [DeviceType.SERVER]: { labelKey: 'deviceType.SERVER', color: 'blue' },
  [DeviceType.NETWORK]: { labelKey: 'deviceType.NETWORK', color: 'green' },
  [DeviceType.OTHER]: { labelKey: 'deviceType.OTHER', color: 'default' }
};

export enum DeviceSubtype {
  STANDALONE = 'standalone',
  CHASSIS = 'chassis',
  NODE = 'node',
  STORAGE = 'storage',
  GPU = 'gpu',
  SWITCH = 'switch',
  ROUTER = 'router',
  FIREWALL = 'firewall',
  PDU = 'pdu',
  UPS = 'ups',
  OTHER = 'other'
}

export const DEVICE_SUBTYPE_MAP: Record<DeviceType, DeviceSubtype[]> = {
  [DeviceType.SERVER]: [
    DeviceSubtype.STANDALONE,
    DeviceSubtype.CHASSIS,
    DeviceSubtype.NODE,
    DeviceSubtype.STORAGE,
    DeviceSubtype.GPU
  ],
  [DeviceType.NETWORK]: [DeviceSubtype.SWITCH, DeviceSubtype.ROUTER, DeviceSubtype.FIREWALL],
  [DeviceType.OTHER]: [DeviceSubtype.PDU, DeviceSubtype.UPS, DeviceSubtype.OTHER]
};

export type DeviceSubtypeKey =
  | 'deviceSubtype.STANDALONE'
  | 'deviceSubtype.CHASSIS'
  | 'deviceSubtype.NODE'
  | 'deviceSubtype.STORAGE'
  | 'deviceSubtype.GPU'
  | 'deviceSubtype.SWITCH'
  | 'deviceSubtype.ROUTER'
  | 'deviceSubtype.FIREWALL'
  | 'deviceSubtype.PDU'
  | 'deviceSubtype.UPS'
  | 'deviceSubtype.OTHER';

export const DEVICE_SUBTYPE_LABEL_KEYS: Record<DeviceSubtype, DeviceSubtypeKey> = {
  [DeviceSubtype.STANDALONE]: 'deviceSubtype.STANDALONE',
  [DeviceSubtype.CHASSIS]: 'deviceSubtype.CHASSIS',
  [DeviceSubtype.NODE]: 'deviceSubtype.NODE',
  [DeviceSubtype.STORAGE]: 'deviceSubtype.STORAGE',
  [DeviceSubtype.GPU]: 'deviceSubtype.GPU',
  [DeviceSubtype.SWITCH]: 'deviceSubtype.SWITCH',
  [DeviceSubtype.ROUTER]: 'deviceSubtype.ROUTER',
  [DeviceSubtype.FIREWALL]: 'deviceSubtype.FIREWALL',
  [DeviceSubtype.PDU]: 'deviceSubtype.PDU',
  [DeviceSubtype.UPS]: 'deviceSubtype.UPS',
  [DeviceSubtype.OTHER]: 'deviceSubtype.OTHER'
};

export const DEVICE_SUBTYPE_COLORS: Record<DeviceSubtype, string> = {
  [DeviceSubtype.STANDALONE]: 'blue',
  [DeviceSubtype.CHASSIS]: 'green',
  [DeviceSubtype.NODE]: 'orange',
  [DeviceSubtype.STORAGE]: 'purple',
  [DeviceSubtype.GPU]: 'magenta',
  [DeviceSubtype.SWITCH]: 'cyan',
  [DeviceSubtype.ROUTER]: 'geekblue',
  [DeviceSubtype.FIREWALL]: 'red',
  [DeviceSubtype.PDU]: 'gold',
  [DeviceSubtype.UPS]: 'lime',
  [DeviceSubtype.OTHER]: 'default'
};


export enum LinkType {
  DEVICE_TO_NETWORK = 'device_to_network',
  NETWORK_TO_NETWORK = 'network_to_network'
}

export enum ImportExportType {
  DEVICE = 'device',
  CUSTOMER = 'customer',
  CABINET = 'cabinet'
}

export enum SSHAction {
  ENABLE = 'enable',
  DISABLE = 'disable',
  SPEED_LIMIT = 'speed_limit',
  SET_VLAN = 'set_vlan',
  SET_TRUNK = 'set_trunk',
  CONFIGURE_IP = 'configure_ip',
  DELETE_CONFIG = 'delete_config'
}



/**
 * 端口占用状态映射（网卡端口 / 交换机端口的 usage_status 字符串）
 * - free: 空闲（可用）→ 绿
 * - occupied: 占用（已用）→ 蓝
 * - disabled: 禁用 → 默认灰
 * - error: 异常 → 红
 * 注意：与 status-codes.generated.ts 中的后端 PortStatus（int 0/1/2）是不同域，勿混淆。
 */
export type PortUsageStatusKey =
  | 'portUsage.FREE'
  | 'portUsage.OCCUPIED'
  | 'portUsage.DISABLED'
  | 'portUsage.ERROR';

export const PORT_USAGE_STATUS_MAP: Record<
  string,
  { labelKey: PortUsageStatusKey; color: string }
> = {
  free: { labelKey: 'portUsage.FREE', color: 'green' },
  occupied: { labelKey: 'portUsage.OCCUPIED', color: 'blue' },
  disabled: { labelKey: 'portUsage.DISABLED', color: 'default' },
  error: { labelKey: 'portUsage.ERROR', color: 'red' }
};

/**
 * 端口占用状态 → 色块背景色（十六进制，供图形化色块使用；与 PORT_USAGE_STATUS_MAP 语义一致）
 */
export const PORT_STATUS_BG_COLOR: Record<string, string> = {
  free: '#52c41a',
  occupied: '#1677ff',
  disabled: '#bfbfbf',
  error: '#ff4d4f'
};

/**
 * 连接活跃状态映射（由后端 device_connection.status 字符串 active/inactive 推导）
 * - active: 活跃 → 绿
 * - inactive: 不活跃 → 默认灰
 */
export type ConnectionStatusKey = 'connectionStatus.ACTIVE' | 'connectionStatus.INACTIVE';

export const CONNECTION_STATUS_MAP: Record<
  string,
  { labelKey: ConnectionStatusKey; color: string }
> = {
  active: { labelKey: 'connectionStatus.ACTIVE', color: 'green' },
  inactive: { labelKey: 'connectionStatus.INACTIVE', color: 'default' }
};

/**
 * 端口链路状态映射（up / down / admin_down / disabled，纯展示）
 * - up: 在线 → 绿（success）
 * - down: 离线 → 红（error）
 * - admin_down: 管理关闭 → 默认灰
 * - disabled: 已禁用 → 默认灰
 */
export type LinkStatusKey =
  | 'linkStatus.UP'
  | 'linkStatus.DOWN'
  | 'linkStatus.ADMIN_DOWN'
  | 'linkStatus.DISABLED';

export const LINK_STATUS_MAP: Record<string, { labelKey: LinkStatusKey; color: string }> = {
  up: { labelKey: 'linkStatus.UP', color: 'success' },
  down: { labelKey: 'linkStatus.DOWN', color: 'error' },
  admin_down: { labelKey: 'linkStatus.ADMIN_DOWN', color: 'default' },
  disabled: { labelKey: 'linkStatus.DISABLED', color: 'default' }
};

/**
 * 拓扑节点状态映射（online / offline / warning，纯展示）
 * - online: 在线 → 绿（success）
 * - offline: 离线 → 默认灰
 * - warning: 告警 → 橙（warning）
 */
export type NodeStatusKey =
  | 'nodeStatus.ONLINE'
  | 'nodeStatus.OFFLINE'
  | 'nodeStatus.WARNING';

export const NODE_STATUS_MAP: Record<string, { labelKey: NodeStatusKey; color: string }> = {
  online: { labelKey: 'nodeStatus.ONLINE', color: 'success' },
  offline: { labelKey: 'nodeStatus.OFFLINE', color: 'default' },
  warning: { labelKey: 'nodeStatus.WARNING', color: 'warning' }
};

export type LoginTypeKey =
  | 'loginType.WEB'
  | 'loginType.WECHAT'
  | 'loginType.API'
  | 'loginType.MOBILE'
  | 'loginType.TOKEN';

export const LOGIN_TYPE_MAP: Record<string, { labelKey: LoginTypeKey; color: string }> = {
  web: { labelKey: 'loginType.WEB', color: 'blue' },
  wechat: { labelKey: 'loginType.WECHAT', color: 'green' },
  api: { labelKey: 'loginType.API', color: 'orange' },
  mobile: { labelKey: 'loginType.MOBILE', color: 'purple' },
  token: { labelKey: 'loginType.TOKEN', color: 'cyan' }
};

export type AuthMethodKey = 'authMethod.PASSWORD' | 'authMethod.CERTIFICATE';

export const AUTH_METHOD_LABEL_KEYS: Record<string, AuthMethodKey> = {
  password: 'authMethod.PASSWORD',
  certificate: 'authMethod.CERTIFICATE'
};



export const MONITOR_PROTOCOL_OPTIONS = [
  { value: 'snmp', label: 'SNMP' },
  { value: 'ipmi', label: 'IPMI' },
  { value: 'zabbix', label: 'Zabbix' },
  { value: 'ping', label: 'Ping' }
];

export const MONITOR_PROTOCOL_COLOR_MAP: Record<string, string> = {
  snmp: 'blue',
  ipmi: 'geekblue',
  zabbix: 'orange',
  ping: 'green'
};

export const MONITOR_PROTOCOL_PALETTE: Record<string, string> = {
  snmp: '#1677ff',
  ipmi: '#2f54eb',
  zabbix: '#faad14',
  ping: '#52c41a'
};

export type NetworkLayerKey = 'networkLayer.L2' | 'networkLayer.L3';

export const NETWORK_LAYER_LABEL_KEYS: Record<number, NetworkLayerKey> = {
  2: 'networkLayer.L2',
  3: 'networkLayer.L3'
};

export type SeverityKey = 'severity.CRITICAL' | 'severity.WARNING' | 'severity.INFO';

export const SEVERITY_LABEL_KEYS: Record<string, SeverityKey> = {
  critical: 'severity.CRITICAL',
  warning: 'severity.WARNING',
  info: 'severity.INFO'
};

export const SEVERITY_COLOR_MAP: Record<string, string> = {
  critical: 'red',
  warning: 'gold',
  info: 'blue'
};

export type ChannelKey =
  | 'channel.INBOX'
  | 'channel.EMAIL'
  | 'channel.VOICE'
  | 'channel.WECHAT_WORK'
  | 'channel.FEISHU'
  | 'channel.DINGTALK'
  | 'channel.CUSTOM';

export const CHANNEL_LABEL_KEYS: Record<string, ChannelKey> = {
  inbox: 'channel.INBOX',
  email: 'channel.EMAIL',
  voice: 'channel.VOICE',
  wechat_work: 'channel.WECHAT_WORK',
  feishu: 'channel.FEISHU',
  dingtalk: 'channel.DINGTALK',
  custom: 'channel.CUSTOM'
};

export const CHANNEL_COLORS: Record<string, string> = {
  inbox: 'blue',
  email: 'cyan',
  voice: 'purple',
  wechat_work: 'green',
  feishu: 'blue',
  dingtalk: 'geekblue',
  custom: 'default'
};

export const BROADCAST_CHANNELS = ['wechat_work', 'feishu', 'dingtalk', 'custom'];
