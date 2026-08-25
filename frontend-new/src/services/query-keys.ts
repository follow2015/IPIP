/**
 * 集中式 Query Key 工厂（新增文件）
 *
 * 为什么需要这个文件？
 * - 原来每个 service 文件各自定义 `const ROOMS_KEY = 'rooms'`，
 *   跨文件 invalidateQueries 时只能手写字符串，存在拼写出错风险。
 * - TanStack Query 推荐用层级数组 key，便于精确或模糊失效。
 * - 统一管理后，key 变更只需改一处。
 *
 * 用法：
 *   queryKey: queryKeys.rooms.detail(id)
 *   queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all })
 */

export const queryKeys = {
  
  rooms: {
    all: ['rooms'] as const,
    list: (p?: unknown) => ['rooms', 'list', p] as const,
    detail: (id: number) => ['rooms', id] as const,
    cabinets: (id: number) => ['rooms', id, 'cabinets'] as const,
    devices: (id: number) => ['rooms', id, 'devices'] as const,
    statistics: (id: number) => ['rooms', id, 'stats'] as const,
    options: ['rooms', 'options'] as const
  },

  
  cabinets: {
    all: ['cabinets'] as const,
    list: (p?: unknown) => ['cabinets', 'list', p] as const,
    detail: (id: number) => ['cabinets', id] as const,
    withDevices: (id: number) => ['cabinets', id, 'with-devices'] as const,
    devices: (id: number) => ['cabinets', id, 'devices'] as const,
    utilization: (id: number) => ['cabinets', id, 'utilization'] as const,
    usageMap: (id: number) => ['cabinets', id, 'usage-map'] as const,
    stats: (id: number) => ['cabinets', id, 'stats'] as const,
    options: (roomId?: number) => ['cabinets', 'options', roomId ?? null] as const
  },

  
  devices: {
    all: ['devices'] as const,
    list: (p?: unknown) => ['devices', 'list', p] as const,
    detail: (id: number) => ['devices', id] as const,
    statistics: ['devices', 'statistics'] as const,
    nics: (id: number) => ['devices', id, 'nics'] as const,
    storage: (id: number) => ['devices', id, 'storage'] as const,
    storageDetail: (id: number) => ['devices', id, 'storage', 'detail'] as const,
    connections: (id: number) => ['devices', id, 'connections'] as const,
    switchPorts: (id: number) => ['devices', id, 'switch-ports'] as const,
    networkPorts: (id: number) => ['devices', id, 'network-ports'] as const,
    portSyncEnabled: (id: number) => ['devices', id, 'port-sync-enabled'] as const
  },

  
  customers: {
    all: ['customers'] as const,
    list: (p?: unknown) => ['customers', 'list', p] as const,
    detail: (id: number) => ['customers', id] as const,
    cabinets: (id: number) => ['customers', id, 'cabinets'] as const,
    devices: (id: number) => ['customers', id, 'devices'] as const,
    assets: (id: number) => ['customers', id, 'assets'] as const,
    statistics: (id: number) => ['customers', id, 'statistics'] as const,
    options: ['customers', 'options'] as const
  },

  
  switches: {
    all: ['switches'] as const,
    list: (p?: unknown) => ['switches', 'list', p] as const,
    detail: (id: number) => ['switches', id] as const,
    withPorts: (id: number) => ['switches', id, 'with-ports'] as const,
    portDetail: (id: number, port: string) => ['switches', id, 'ports', port] as const
  },

  
  ip: {
    all: ['ip_addresses'] as const,
    list: (p?: unknown) => ['ip_addresses', 'list', p] as const,
    detail: (addr: string) => ['ip_addresses', addr] as const
  },

  networks: {
    all: ['networks'] as const,
    list: (p?: unknown) => ['networks', 'list', p] as const,
    ipNetworks: (p?: unknown) => ['ip_networks', p] as const,
    detail: (network: string, p?: unknown) => ['network_detail', network, p] as const
  },

  
  rbac: {
    all: ['rbac'] as const,
    roles: (p?: unknown) => ['rbac', 'roles', p] as const,
    roleDetail: (id: number) => ['rbac', 'roles', id] as const,
    rolePermissions: (id: number) => ['rbac', 'roles', id, 'permissions'] as const,
    permissions: (p?: unknown) => ['rbac', 'permissions', p] as const,
    categories: ['rbac', 'categories'] as const,
    userRoles: (id: number) => ['rbac', 'users', id, 'roles'] as const,
    options: ['rbac', 'options'] as const
  },

  
  users: {
    all: ['users'] as const,
    list: (p?: unknown) => ['users', 'list', p] as const,
    me: ['users', 'me'] as const,
    loginLogs: (p?: unknown) => ['users', 'login-logs', p] as const,
    permissions: (id: number) => ['users', id, 'permissions'] as const
  },

  
  dashboard: {
    stats: ['dashboard', 'stats'] as const
  },

  
  linkAggregation: {
    all: ['linkAggregation'] as const,
    byDevice: (deviceId: number) => ['linkAggregation', 'device', deviceId] as const,
    allGlobal: (roomId?: number, params?: unknown) =>
      ['linkAggregation', 'global', roomId, params] as const,
    detail: (lagId: number) => ['linkAggregation', 'detail', lagId] as const
  },

  
  vlans: {
    all: ['vlans'] as const,
    list: (p?: unknown) => ['vlans', 'list', p] as const,
    detail: (id: number) => ['vlans', 'detail', id] as const,
    byRoom: (roomId: number) => ['vlans', 'byRoom', roomId] as const,
    byDevice: (deviceId: number) => ['vlans', 'byDevice', deviceId] as const
  },

  
  auditLogs: {
    all: ['auditLogs'] as const,
    list: (p?: unknown) => ['auditLogs', 'list', p] as const
  },

  
  deviceConfig: {
    all: ['deviceConfig'] as const,
    detail: (deviceId: number) => ['deviceConfig', 'detail', deviceId] as const,
    history: (deviceId: number) => ['deviceConfig', 'history', deviceId] as const
  },

  
  topology: {
    all: ['topology'] as const,
    network: (p?: unknown) => ['topology', 'network', p] as const,
    device: (p?: unknown) => ['topology', 'device', p] as const,
    autoDetect: ['topology', 'auto-detect'] as const
  },

  
  notifications: {
    all: ['notifications'] as const,
    unreadCount: ['notifications', 'unread-count'] as const,
    list: (p?: unknown) => ['notifications', 'list', p] as const,
    preferences: ['notifications', 'preferences'] as const
  },

  
  webhookConfigs: {
    all: ['webhookConfigs'] as const,
    list: ['webhookConfigs', 'list'] as const
  },

  
  mailSettings: {
    all: ['mailSettings'] as const,
    config: ['mailSettings', 'config'] as const
  },

  
  monitor: {
    status: (deviceId: number) => ['monitor', 'status', deviceId] as const,
    credentials: () => ['monitor', 'credentials'] as const,
    overview: ['monitor', 'overview'] as const,
    statuses: (params?: unknown) => ['monitor', 'statuses', params] as const,
    
    statusesAll: ['monitor', 'statuses'] as const,
    config: ['monitor', 'config'] as const,
    alerts: (params?: unknown) => ['monitor', 'alerts', params] as const,
    
    alertsAll: ['monitor', 'alerts'] as const,
    
    alertDetail: (alertId: number) => ['monitor', 'alerts', alertId] as const,
    alertAggregations: (params: Record<string, unknown> | object) =>
      ['monitor', 'alerts', 'aggregations', params] as const,
    
    alertStatistics: (params: Record<string, unknown> | object) =>
      ['monitor', 'alerts', 'statistics', params] as const,
    linkedDevices: (credentialId: number) =>
      ['monitor', 'credentials', credentialId, 'devices'] as const,
    history: (deviceId: number, params?: unknown) =>
      ['monitor', 'history', deviceId, params] as const,
    trends: (deviceId: number, params?: unknown) =>
      ['monitor', 'trends', deviceId, params] as const,
    metricKeys: (deviceId: number) => ['monitor', 'metric-keys', deviceId] as const,
    
    metricLatest: (deviceId: number) => ['monitor', 'metric-latest', deviceId] as const,
    metricHistory: (deviceId: number, metricKey: string, params?: unknown) =>
      ['monitor', 'metric-history', deviceId, metricKey, params] as const,
    traffic: (deviceId: number, port: string, from: number, till: number) =>
      ['monitor', 'traffic', deviceId, port, from, till] as const,
    metricAlerts: (deviceId: number) => ['monitor', 'metric-alerts', deviceId] as const,
    
    metricAlertsAll: ['monitor', 'metric-alerts'] as const,
    metricDashboard: (deviceId: number) => ['monitor', 'metric-dashboard', deviceId] as const,
    
    metricDashboardAll: ['monitor', 'metric-dashboard'] as const,
    metricTemplates: () => ['monitor', 'metric-templates'] as const,
    metricTemplateGroups: ['monitor', 'metric-template-groups'] as const,
    metricTemplateGroup: (groupId: number) =>
      ['monitor', 'metric-template-groups', groupId] as const,
    silenceRules: () => ['monitor', 'silence-rules'] as const,
    escalationPolicies: () => ['monitor', 'escalation-policies'] as const,
    thresholdOverrides: (params?: unknown) => ['monitor', 'threshold-overrides', params] as const,
    thresholdOverridesAll: ['monitor', 'threshold-overrides'] as const,
    mibScan: () => ['monitor', 'mib-scan'] as const,
    
    silenceRulesCrud: ['monitor', 'silence-rules', 'crud'] as const,
    alertDependencyRulesCrud: ['monitor', 'alert-dependency-rules', 'crud'] as const,
    slaTargetsCrud: ['monitor', 'sla-targets', 'crud'] as const,
    slaAchievements: ['monitor', 'sla-targets', 'achievements'] as const,
    escalationPoliciesCrud: ['monitor', 'escalation-policies', 'crud'] as const,
    oidCategoryRulesCrud: ['monitor', 'oid-category-rules', 'crud'] as const,
    vendorBrandsCrud: ['monitor', 'vendor-brands', 'crud'] as const,
    metricTemplatesCrud: ['monitor', 'metric-templates', 'crud'] as const,
    thresholdOverridesCrud: ['monitor', 'threshold-overrides', 'crud'] as const,
    
    deviceTypeRecommends: ['monitor', 'device-type-recommends'] as const,
    recommendConfig: (deviceType: string) => ['monitor', 'recommend-config', deviceType] as const
  }
} as const;
