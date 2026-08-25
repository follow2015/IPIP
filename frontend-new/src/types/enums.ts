/**
 * 枚举常量与标签映射（前端枚举分层）
 *
 * 单一真相源原则：
 * 1. 后端派生的状态枚举 / 映射 —— 由 app/core/enums.py 经
 *    scripts/generate_frontend_enums.py 自动生成到 ./status-codes.generated.ts。
 *    本文件通过 `export *` 透传，**请勿在此手改后端枚举**（改 enums.py 后运行 `make sync-enums`）。
 * 2. L2 前端独有（API 约定 / 纯展示）枚举与映射 —— 见下方区块，手工维护：
 *    - 设备主类型 / 子类型（前端分类，与后端 cabinet_utils.DeviceType 不同）
 *    - LinkType / ImportExportType / SSHAction / SWITCH_DEVICE_TYPE_OPTIONS（API 约定）
 *    - 端口占用 PORT_USAGE_STATUS_MAP、链路 LINK_STATUS_MAP、节点 NODE_STATUS_MAP、
 *      连接 CONNECTION_STATUS_MAP、登录 LOGIN_TYPE_MAP、认证 AUTH_METHOD_OPTIONS（纯展示）
 */

export * from './status-codes.generated';


export enum DeviceType {
  SERVER = 'server',
  NETWORK = 'network',
  OTHER = 'other'
}


export const DEVICE_TYPE_MAP: Record<DeviceType, { label: string; color: string }> = {
  [DeviceType.SERVER]: { label: '服务器', color: 'blue' },
  [DeviceType.NETWORK]: { label: '网络设备', color: 'green' },
  [DeviceType.OTHER]: { label: '其他设备', color: 'default' }
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


export const DEVICE_SUBTYPE_LABELS: Record<DeviceSubtype, string> = {
  [DeviceSubtype.STANDALONE]: '独立服务器',
  [DeviceSubtype.CHASSIS]: '机箱',
  [DeviceSubtype.NODE]: '节点',
  [DeviceSubtype.STORAGE]: '存储服务器',
  [DeviceSubtype.GPU]: 'GPU服务器',
  [DeviceSubtype.SWITCH]: '交换机',
  [DeviceSubtype.ROUTER]: '路由器',
  [DeviceSubtype.FIREWALL]: '防火墙',
  [DeviceSubtype.PDU]: '配电单元',
  [DeviceSubtype.UPS]: '不间断电源',
  [DeviceSubtype.OTHER]: '其他'
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


export const SWITCH_DEVICE_TYPE_OPTIONS = [
  { label: '华为', value: 'huawei' },
  { label: '思科', value: 'cisco' },
  { label: 'H3C', value: 'h3c' }
];


export const PORT_USAGE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  free: { label: '空闲', color: 'green' },
  occupied: { label: '占用', color: 'blue' },
  disabled: { label: '禁用', color: 'default' },
  error: { label: '异常', color: 'red' }
};


export const PORT_STATUS_BG_COLOR: Record<string, string> = {
  free: '#52c41a',
  occupied: '#1677ff',
  disabled: '#bfbfbf',
  error: '#ff4d4f'
};


export const CONNECTION_STATUS_MAP: Record<string, { label: string; color: string }> = {
  active: { label: '活跃', color: 'green' },
  inactive: { label: '不活跃', color: 'default' }
};


export const LINK_STATUS_MAP: Record<string, { label: string; color: string }> = {
  up: { label: '在线', color: 'success' },
  down: { label: '离线', color: 'error' },
  admin_down: { label: '管理关闭', color: 'default' },
  disabled: { label: '已禁用', color: 'default' }
};


export const NODE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  online: { label: '在线', color: 'success' },
  offline: { label: '离线', color: 'default' },
  warning: { label: '告警', color: 'warning' }
};


export const LOGIN_TYPE_MAP: Record<string, { label: string; color: string }> = {
  web: { label: 'Web', color: 'blue' },
  wechat: { label: '微信', color: 'green' },
  api: { label: 'API', color: 'orange' },
  mobile: { label: '移动端', color: 'purple' },
  token: { label: 'Token', color: 'cyan' }
};


export const AUTH_METHOD_OPTIONS = [
  { label: '密码', value: 'password' },
  { label: '证书', value: 'certificate' }
];


export const SSH_PROTOCOL_OPTIONS = [
  { label: 'SSH', value: 'ssh' },
  { label: 'Telnet', value: 'telnet' }
];


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


export const NETWORK_LAYER_OPTIONS = [
  { label: '二层交换机 (L2)', value: 2 },
  { label: '三层交换机 (L3)', value: 3 }
];


export const SEVERITY_OPTIONS = [
  { label: '严重', value: 'critical' },
  { label: '警告', value: 'warning' },
  { label: '信息', value: 'info' }
];


export const SEVERITY_COLOR_MAP: Record<string, string> = {
  critical: 'red',
  warning: 'gold',
  info: 'blue'
};


export const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '信息'
};


export const CHANNEL_LABELS: Record<string, string> = {
  inbox: '站内信',
  email: '邮件',
  wechat_work: '企业微信',
  feishu: '飞书',
  custom: '自定义'
};


export const CHANNEL_COLORS: Record<string, string> = {
  inbox: 'blue',
  email: 'cyan',
  wechat_work: 'green',
  feishu: 'blue',
  custom: 'default'
};


export const BROADCAST_CHANNEL_OPTIONS = [
  { label: '企业微信', value: 'wechat_work' },
  { label: '飞书', value: 'feishu' },
  { label: '自定义', value: 'custom' }
];
