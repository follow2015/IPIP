/**
 * 业务实体类型定义
 *
 * 迁移策略：
 * - 与 OpenAPI Schema 完全一致的类型 → type alias（从 api-bridge.ts 导入）
 * - 有差异的类型 → 基于 OpenAPI 类型 & 扩展额外字段
 * - 无 OpenAPI 对应的类型 → 保持手写
 *
 * 生成命令：npm run generate:all
 */
import type {
  User as OApiUser,
  Room as OApiRoom,
  Cabinet as OApiCabinet,
  Device as OApiDevice,
  DeviceNicPort as OApiDeviceNicPort,
  DeviceConnection as OApiDeviceConnection,
  DeviceStorage as OApiDeviceStorageDetail,
  Customer as OApiCustomer,
  IPAddress as OApiIPAddress,
  IPAddressDetail as OApiIPAddressDetail,
  Switch as OApiSwitch,
  SwitchPort as OApiSwitchPort,
  SwitchPortIP as OApiSwitchPortIP,
  Permission as OApiPermission,
  Role as OApiRole,
  AuditLog as OApiAuditLog,
  VLAN as OApiVLAN,
  LinkAggregationGroup as OApiLinkAggregationGroup,
  IPNetwork as OApiIPNetwork,
  DeviceConfigBackup as OApiDeviceConfigBackup,
  DeviceConfigChange as OApiDeviceConfigChange,
  LoginData as OApiLoginData,
  VerifyData as OApiVerifyData,
  TopologyNode as OApiTopologyNode,
  TopologyEdge as OApiTopologyEdge,
  TopologyStats as OApiTopologyStats,
  TopologyAutoDetectChange as OApiTopologyAutoDetectChange
} from './api-bridge';


export type User = OApiUser;


export type VerifyData = OApiVerifyData;


export interface LoginData extends Omit<OApiLoginData, 'user'> {
  user: OApiLoginData['user'] & {
    
    name: string;
    
    roles: string[];
    
    is_active: boolean;
    
    status: number;
  };
}


export interface Room extends OApiRoom {
  
  cabinets?: Cabinet[];
}


export interface Cabinet extends OApiCabinet {
  
  devices?: Device[];
  used_u_positions?: number[];
  available_u_ranges?: Array<{ start: number; end: number; count: number }>;
}


export interface CabinetUtilization {
  total_u: number;
  used_u: number;
  available_u: number;
  usage_rate: number;
}


export interface CabinetUsageMap {
  [uPosition: number]: {
    device_id: number;
    device_name: string;
    height_u: number;
  };
}


export interface CabinetStats {
  total_devices: number;
  total_power: number;
  used_power: number;
  power_usage_rate: number;
}


export type Device = OApiDevice & {
  
  nic_ports?: DeviceNicPort[];
  storage_items?: DeviceStorageDetail[];
  
  peer_port_names?: string[] | null;
  
  monitor_summary?: {
    
    ping_reachable: boolean | null;
    
    has_monitor_credential: boolean;
    
    monitor_reachable: boolean | null;
    
    monitor_protocol: string | null;
    active_metric_alerts: number;
    max_alert_severity: number;
    monitor_interrupted: boolean;
  };
  
  deleted_location_snapshot?: {
    cabinet_id?: number;
    cabinet_number?: string;
    u_position?: number;
    height_u?: number;
    original_status?: number;
    parent_device_id?: number;
    node_position?: number;
    node_row?: number;
    node_col?: number;
  } | null;
  deleted_children_snapshot?: Record<string, unknown>[] | null;
};


export type DeviceNicPort = OApiDeviceNicPort;


export type DeviceConnection = OApiDeviceConnection;


export type DeviceStorageDetail = OApiDeviceStorageDetail;


export interface DeviceStorageGrouped {
  storage_type: string;
  capacity: string;
  interface_type: string | null;
  manufacturer: string | null;
  model: string | null;
  total_count: number;
  serial_numbers: string[];
}


export interface DeviceStorageResponse {
  storage: DeviceStorageDetail[] | DeviceStorageGrouped[];
}


export interface DevicePortsResponse {
  ports: DeviceNicPort[];
}


export interface DeviceNodesResponse {
  nodes: Device[];
}


export type IPAddress = OApiIPAddress;


export type IPAddressDetail = OApiIPAddressDetail;


export interface IPScanResult {
  ip_address: string;
  open_ports: number[];
}


export interface PingResult {
  ip_address: string;
  reachable: boolean;
}


export type Switch = OApiSwitch & {
  
  peer_port_names?: string[] | null;
};


export interface SwitchPort extends OApiSwitchPort {
  
  status?: string;
  
  mac?: string;
  
  raw_info?: string;
}


export type SwitchPortIP = OApiSwitchPortIP;


export interface SwitchPortDetail {
  port?: string;
  status?: string;
  vlan?: number | null;
  speed?: string | null;
  description?: string;
  ip_address?: string | null;
  ip_list: SwitchPortIP[];
  updated_at: string;
  mac_address: string | null;
  port_mac: string | null;
  has_port_config?: boolean;
  port_config_updated_at?: string | null;
  vlan_ports?: string[];
  vlan_config?: string;
  trunk_members?: string[];
  trunk_config?: string;
  eth_trunk_id?: number;
}


export interface PortConfigResult {
  port_config: string;
  updated_at: string | null;
  from_cache: boolean;
  vlan_ports?: string[];
  trunk_members?: string[];
}


export interface SwitchWithPortsResponse {
  switch: Switch;
  ports: SwitchPort[];
}


export interface Customer extends OApiCustomer {
  
  cabinets?: Cabinet[];
  devices?: Device[];
}


export interface CustomerAssets {
  customer_name: string;
  customer_status: number;
  rooms: Array<{ id: number; name: string; location: string | null }>;
  cabinets: {
    full_cabinets: Cabinet[];
    partial_cabinets: Cabinet[];
    total_count: number;
    total_u_used: number;
  };
  devices: {
    total_count: number;
    by_type: Record<string, number>;
    by_cabinet: Record<string, number>;
  };
  networks: {
    full_networks: unknown[];
    partial_ips: IPAddress[];
    total_networks: number;
    total_ips: number;
  };
  summary: {
    total_rooms: number;
    total_cabinets: number;
    full_cabinets: number;
    partial_cabinets: number;
    total_devices: number;
    full_cabinet_devices: number;
    partial_cabinet_devices: number;
    total_networks: number;
    total_ips: number;
    full_networks: number;
    partial_ips: number;
  };
}


export type Role = OApiRole;


export type Permission = OApiPermission;


export interface RoleDetail {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  status: number;
  created_at: string;
  updated_at: string;
  permissions: string[];
  users: number[];
  permission_count?: number;
  user_count?: number;
}


export interface IPStatusGroup {
  total: number;
  active: number;
  inactive: number;
  blocked: number;
  unused: number;
}


export interface DashboardStats {
  rooms: { total: number; active: number };
  cabinets: {
    total: number;
    occupied: number;
    available: number;
    maintenance: number;
    reserved: number;
    disabled: number;
    utilization: number;
  };
  devices: {
    total: number;
    online: number;
    offline: number;
    
    status_distribution: Record<string, number>;
  };
  networks: {
    segments: number;
    ips_total: number;
    ips_used: number;
    ips_inactive: number;
    ips_blocked: number;
    ips_available: number;
    switches: number;
    ports_total: number;
    ports_used: number;
    public_ips: IPStatusGroup;
    private_ips: IPStatusGroup;
  };
  customers: { total: number; active: number; inactive: number };
  switches: { total: number };
  percentages: {
    device_online_rate: number;
    cabinet_utilization: number;
    ip_utilization: number;
    port_utilization: number;
  };
}


export interface DashboardActivity {
  id: number;
  title: string;
  description: string;
  user: string;
  timestamp: string | null;
  icon: string;
  color: string;
}


export interface SystemStatus {
  overall: 'healthy' | 'warning' | 'critical' | 'unknown';
  performance: {
    cpu: number;
    memory: number;
    disk: number;
    memory_total: number;
    memory_used: number;
    disk_total: number;
    disk_used: number;
  };
  services: {
    database: string;
    api: string;
    frontend: string;
  };
  lastUpdated: string;
  error?: string;
}


export interface ImportResult {
  total: number;
  imported_count: number;
  failed_count: number;
  failed_rows: number[];
}


export interface BatchCreateItemResult {
  index: number;
  device_name: string;
  success: boolean;
  device_id?: number;
  error?: string;
}


export interface BatchCreateResult {
  total: number;
  success_count: number;
  failed_count: number;
  results: BatchCreateItemResult[];
}


export interface CloneDeviceData {
  device_type: string;
  device_subtype?: string;
  brand?: string;
  device_model?: string;
  height_u?: number;
  status?: number;
  cpu?: string;
  cpu_way?: number;
  cpu_cores?: number;
  memory?: string;
  memory_size_gb?: number;
  storage_summary?: string;
  os_version?: string;
  cabinet_id?: number;
  power?: number;
  responsible_person?: number;
  customer_id?: number;
  notes?: string;
  [key: string]: unknown;
}


export interface SSHOperationRequest {
  action:
    | 'enable'
    | 'disable'
    | 'speed_limit'
    | 'set_vlan'
    | 'set_trunk'
    | 'configure_ip'
    | 'delete_config';
  params?: Record<string, unknown>;
}


export interface PortScanResult {
  ip: string;
  open_ports: number[];
  scanned_at: string;
}


export type IPNetwork = OApiIPNetwork;


export interface NetworkInfo {
  network: string;
  version: string;
  total_ips: number | null;
  usable_ips: number | null;
  subnet_mask: string | null;
  gateway: string | null;
  start_ip: string | null;
  end_ip: string | null;
  network_address: string | null;
  broadcast_address: string | null;
  updated_at?: string | null;
  notes?: string | null;
  switch_name?: string | null;
  room_name?: string | null;
  customer_name?: string | null;
  switch_id?: number | null;
  room_id?: number;
  port?: string | null;
  nexthop?: string | null;
}


export interface NetworkInfoListItem {
  switch_id: number | null;
  port: string | null;
  nexthop: string | null;
  updated_at: string | null;
  notes: string | null;
  switch_name: string | null;
  room_name: string | null;
  customer_name: string | null;
}


export interface NetworkDetailResponse {
  ip_addresses: NetworkIPAddress[];
  total: number;
  ip_status_count: Record<string, number>;
  network_info: NetworkInfo;
  network_info_list: NetworkInfoListItem[];
  page: number;
  page_size: number;
  total_pages: number;
}


export interface NetworkIPAddress {
  ip_address: string;
  mac_address: string;
  switch_name: string | null;
  port: string | null;
  room_name: string | null;
  customer_name: string | null;
  notes: string | null;
  status: number;
  updated_at: string | null;
}


export interface NetworkListResponse {
  data: IPNetwork[];
  pagination: {
    page: number;
    total_pages: number;
    total: number;
    page_size: number;
  };
}


export interface IPNetworkListResponse {
  networks: IPNetwork[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}


export type AuditLog = OApiAuditLog;


export interface IPAllocationLog {
  id: number;
  ip_address: string;
  room_id: number;
  action: 'allocate' | 'release' | 'change_status';
  old_status: number | null;
  new_status: number | null;
  operator_id: number;
  detail: Record<string, unknown> | null;
  created_at: string;
}


export type VLAN = OApiVLAN;


export type LinkAggregationGroup = OApiLinkAggregationGroup;


export type DeviceConfigBackup = OApiDeviceConfigBackup;


export type DeviceConfigChange = OApiDeviceConfigChange;


export type TopologyNode = OApiTopologyNode;


export type TopologyEdge = OApiTopologyEdge;


export type TopologyStats = OApiTopologyStats;


export type TopologyAutoDetectChange = OApiTopologyAutoDetectChange;


export interface VirtualRoomMember {
  virtual_room_id: number;
  device_id: number;
  device_name?: string;
  device_ip?: string;
  room_id?: number;
  room_name?: string;
}


export interface VirtualRoom {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  last_scan_at: string | null;
  last_scan_scope: string | null;
  member_count: number;
  members?: VirtualRoomMember[];
}


export interface ScanProgress {
  scope: string;
  room_id: number;
  total: number;
  completed: number;
  failed: number;
  phase: string;
  reason?: string;
  elapsed_seconds: number;
  eta_seconds: number;
}
