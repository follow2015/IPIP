import { queryKeys } from './query-keys';

export const CACHE_KEY_GROUPS = {
  rooms: queryKeys.rooms.all,
  cabinets: queryKeys.cabinets.all,
  devices: queryKeys.devices.all,
  customers: queryKeys.customers.all,
  networks: queryKeys.networks.all,
  ip: queryKeys.ip.all,
  monitorStatuses: queryKeys.monitor.statusesAll,
  monitorAlerts: queryKeys.monitor.alertsAll,
  monitorMetricAlerts: queryKeys.monitor.metricAlertsAll,
  monitorOverview: queryKeys.monitor.overview,
  monitorMetricDashboard: queryKeys.monitor.metricDashboardAll,
  switches: queryKeys.switches.all,
  vlans: queryKeys.vlans.all,
  users: queryKeys.users.all,
  rbac: queryKeys.rbac.all,
  dashboard: queryKeys.dashboard.stats,
  topology: queryKeys.topology.all,
  auditLogs: queryKeys.auditLogs.all
} as const;

export type CacheKeyGroup = keyof typeof CACHE_KEY_GROUPS;
export type CacheResource = keyof typeof INVALIDATION_MATRIX;

export const INVALIDATION_MATRIX = {
  cabinet: ['cabinets', 'devices', 'rooms', 'dashboard'],
  device: [
    'devices',
    'cabinets',
    'rooms',
    'monitorStatuses',
    'monitorAlerts',
    'monitorMetricAlerts',
    'monitorOverview',
    'monitorMetricDashboard',
    'dashboard',
    'topology'
  ],
  customer: ['customers', 'cabinets', 'devices', 'networks', 'ip', 'rooms', 'dashboard'],
  room: ['dashboard'],
  switch: ['switches', 'devices', 'topology', 'monitorOverview'],
  vlan: ['vlans', 'switches', 'devices'],
  user: ['users', 'auditLogs'],
  rbacRole: ['rbac', 'users']
} as const satisfies Record<string, readonly CacheKeyGroup[]>;

type QueryClientLike = { invalidateQueries: (opts: { queryKey: unknown[] }) => unknown };

export function invalidateResourceGraph(qc: QueryClientLike | undefined, resource: CacheResource) {
  if (!qc) return;
  for (const group of INVALIDATION_MATRIX[resource] ?? []) {
    const key = CACHE_KEY_GROUPS[group as CacheKeyGroup];
    if (!key) continue; // 表与映射不同源的情况由门禁拦截，这里不抛（失效失败不该炸页面）
    qc.invalidateQueries({ queryKey: [...key] });
  }
}

export const invalidateCabinetGraph = (qc?: QueryClientLike) =>
  invalidateResourceGraph(qc, 'cabinet');
export const invalidateDeviceGraph = (qc?: QueryClientLike) =>
  invalidateResourceGraph(qc, 'device');
export const invalidateCustomerGraph = (qc?: QueryClientLike) =>
  invalidateResourceGraph(qc, 'customer');
