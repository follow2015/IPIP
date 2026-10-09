
export type PermissionCode =
  | 'room:view'
  | 'cabinet:view'
  | 'device:view'
  | 'customer:view'
  | 'carrier:view'
  | 'circuit:view'
  | 'ip:view'
  | 'switch:view'
  | 'network:view'
  | 'monitor:view'
  | 'monitor:config'
  | 'ai:use'
  | 'ai:admin'
  | 'ai:agentic'
  | 'user:view'
  | 'rbac:view'
  | 'audit:view'
  | 'import:view';

export const ROUTE_PERMISSIONS: Record<string, PermissionCode> = {
  rooms: 'room:view',
  'rooms/overview': 'room:view',
  'rooms/:id': 'room:view',
  cabinets: 'cabinet:view',
  'cabinets/:id': 'cabinet:view',
  devices: 'device:view',
  'devices/:id': 'device:view',
  'device-recycle-bin': 'device:view',
  customers: 'customer:view',
  'customers/:id': 'customer:view',
  carriers: 'carrier:view',
  circuits: 'circuit:view',
  'settings/component-templates': 'customer:view',
  'asset/vendor-brands': 'monitor:config',

  ip: 'ip:view',
  'ip/audit': 'ip:view',
  switches: 'switch:view',
  'switches/:id': 'switch:view',
  network: 'network:view',
  'network/:ipNetwork': 'network:view',
  vlans: 'switch:view',
  'link-aggregations': 'switch:view',
  topology: 'switch:view',
  'virtual-rooms': 'switch:view',

  'monitor/overview': 'monitor:view',
  'monitor/alerts': 'monitor:view',
  'monitor/incidents': 'monitor:view',
  'monitor/history': 'monitor:view',
  'monitor/credentials': 'monitor:view',
  'monitor/settings': 'monitor:view',
  'monitor/alert-rules': 'monitor:config',
  'monitor/thresholds': 'monitor:config',
  'monitor/oid-tools': 'monitor:config',
  '/monitor/noc-screen/fullscreen': 'monitor:view',

  'ai/nlq': 'ai:use',
  'ai/rag': 'ai:use',
  'ai/skills': 'ai:admin',
  'ai/config': 'ai:admin',
  'ai/monitor': 'ai:admin',
  'ai/audit': 'ai:admin',
  'ai/diagnosis': 'ai:agentic',

  users: 'user:view',
  rbac: 'rbac:view',
  'login-logs': 'user:view',
  'audit-logs': 'audit:view',
  'settings/webhook-configs': 'user:view',
  'settings/mail': 'user:view',
  'settings/voice': 'user:view',
  'import-export': 'import:view'
};

export const PUBLIC_ROUTE_PATHS: readonly string[] = [
  '/login',
  '/',
  'dashboard',
  'profile',
  'settings/notification-preferences',
  'settings/licenses',
  '*'
];
