/**
 * 菜单配置常量
 * - 供 Sidebar 和 AppLayout 共享使用
 * - 菜单项的 key/label/path 用于 TabBar 标签页同步
 */
import React from 'react';
import {
  DashboardOutlined,
  HomeOutlined,
  DatabaseOutlined,
  MedicineBoxOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  SwapOutlined,
  ApartmentOutlined,
  ImportOutlined,
  TeamOutlined,
  UserOutlined,
  SafetyOutlined,
  FileSearchOutlined,
  PartitionOutlined,
  GroupOutlined,
  AuditOutlined,
  AppstoreOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  ClusterOutlined,
  BellOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  MailOutlined,
  PhoneOutlined,
  MonitorOutlined,
  LineChartOutlined,
  SettingOutlined,
  AlertOutlined,
  ControlOutlined,
  ReadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined
} from '@ant-design/icons';

export type MenuLabelKey =
  | 'menu.dashboard'
  | 'menu.asset'
  | 'menu.rooms'
  | 'menu.cabinets'
  | 'menu.devices'
  | 'menu.deviceRecycleBin'
  | 'menu.customers'
  | 'menu.componentTemplates'
  | 'menu.vendorBrands'
  | 'menu.networkGroup'
  | 'menu.ip'
  | 'menu.ipAudit'
  | 'menu.switches'
  | 'menu.network'
  | 'menu.vlans'
  | 'menu.linkAggregations'
  | 'menu.topology'
  | 'menu.virtualRooms'
  | 'menu.monitor'
  | 'menu.monitorOverview'
  | 'menu.monitorAlerts'
  | 'menu.monitorIncidents'
  | 'menu.monitorHistory'
  | 'menu.monitorCredentials'
  | 'menu.monitorSettings'
  | 'menu.monitorAlertRules'
  | 'menu.monitorThresholds'
  | 'menu.monitorOidTools'
  | 'menu.ai'
  | 'menu.aiNlq'
  | 'menu.aiSkills'
  | 'menu.aiConfig'
  | 'menu.aiMonitor'
  | 'menu.aiAudit'
  | 'menu.aiRag'
  | 'menu.aiDiagnosis'
  | 'menu.system'
  | 'menu.users'
  | 'menu.rbac'
  | 'menu.loginLogs'
  | 'menu.auditLogs'
  | 'menu.notificationPreferences'
  | 'menu.webhookConfigs'
  | 'menu.mailSettings'
  | 'menu.voiceSettings'
  | 'menu.importExport'
  | 'menu.licenses';

export interface MenuConfig {
  key: string;
  labelKey: MenuLabelKey;
  icon: React.ReactNode;
  path: string;
  permission?: string;
  children?: MenuConfig[];
}

export const MENU_CONFIGS: MenuConfig[] = [
  { key: 'dashboard', labelKey: 'menu.dashboard', icon: <DashboardOutlined />, path: '/dashboard' },
  {
    key: 'asset',
    labelKey: 'menu.asset',
    icon: <HomeOutlined />,
    path: '/rooms',
    permission: 'room:view',
    children: [
      {
        key: 'rooms',
        labelKey: 'menu.rooms',
        icon: <HomeOutlined />,
        path: '/rooms',
        permission: 'room:view'
      },
      {
        key: 'cabinets',
        labelKey: 'menu.cabinets',
        icon: <DatabaseOutlined />,
        path: '/cabinets',
        permission: 'cabinet:view'
      },
      {
        key: 'devices',
        labelKey: 'menu.devices',
        icon: <CloudServerOutlined />,
        path: '/devices',
        permission: 'device:view'
      },
      {
        key: 'device-recycle-bin',
        labelKey: 'menu.deviceRecycleBin',
        icon: <DeleteOutlined />,
        path: '/device-recycle-bin',
        permission: 'device:view'
      },
      {
        key: 'customers',
        labelKey: 'menu.customers',
        icon: <TeamOutlined />,
        path: '/customers',
        permission: 'customer:view'
      },
      {
        key: 'component-templates',
        labelKey: 'menu.componentTemplates',
        icon: <AppstoreOutlined />,
        path: '/settings/component-templates',
        permission: 'customer:view'
      },
      {
        key: 'vendor-brands',
        labelKey: 'menu.vendorBrands',
        icon: <SafetyOutlined />,
        path: '/asset/vendor-brands',
        permission: 'monitor:config'
      }
    ]
  },
  {
    key: 'network-group',
    labelKey: 'menu.networkGroup',
    icon: <ApartmentOutlined />,
    path: '/ip',
    permission: 'ip:view',
    children: [
      {
        key: 'ip',
        labelKey: 'menu.ip',
        icon: <GlobalOutlined />,
        path: '/ip',
        permission: 'ip:view'
      },
      {
        key: 'ip-audit',
        labelKey: 'menu.ipAudit',
        icon: <FileSearchOutlined />,
        path: '/ip/audit',
        permission: 'ip:view'
      },
      {
        key: 'switches',
        labelKey: 'menu.switches',
        icon: <SwapOutlined />,
        path: '/switches',
        permission: 'switch:view'
      },
      {
        key: 'network',
        labelKey: 'menu.network',
        icon: <ApartmentOutlined />,
        path: '/network',
        permission: 'network:view'
      },
      {
        key: 'vlans',
        labelKey: 'menu.vlans',
        icon: <PartitionOutlined />,
        path: '/vlans',
        permission: 'switch:view'
      },
      {
        key: 'link-aggregations',
        labelKey: 'menu.linkAggregations',
        icon: <GroupOutlined />,
        path: '/link-aggregations',
        permission: 'switch:view'
      },
      {
        key: 'topology',
        labelKey: 'menu.topology',
        icon: <DeploymentUnitOutlined />,
        path: '/topology',
        permission: 'switch:view'
      },
      {
        key: 'virtual-rooms',
        labelKey: 'menu.virtualRooms',
        icon: <ClusterOutlined />,
        path: '/virtual-rooms',
        permission: 'switch:view'
      }
    ]
  },
  {
    key: 'monitor',
    labelKey: 'menu.monitor',
    icon: <MonitorOutlined />,
    path: '/monitor',
    permission: 'monitor:view',
    children: [
      {
        key: 'monitor-overview',
        labelKey: 'menu.monitorOverview',
        icon: <MonitorOutlined />,
        path: '/monitor/overview',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-alerts',
        labelKey: 'menu.monitorAlerts',
        icon: <BellOutlined />,
        path: '/monitor/alerts',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-incidents',
        labelKey: 'menu.monitorIncidents',
        icon: <ThunderboltOutlined />,
        path: '/monitor/incidents',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-history',
        labelKey: 'menu.monitorHistory',
        icon: <LineChartOutlined />,
        path: '/monitor/history',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-credentials',
        labelKey: 'menu.monitorCredentials',
        icon: <SafetyOutlined />,
        path: '/monitor/credentials',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-settings',
        labelKey: 'menu.monitorSettings',
        icon: <ApiOutlined />,
        path: '/monitor/settings',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-alert-rules',
        labelKey: 'menu.monitorAlertRules',
        icon: <AlertOutlined />,
        path: '/monitor/alert-rules',
        permission: 'monitor:config'
      },
      {
        key: 'monitor-thresholds',
        labelKey: 'menu.monitorThresholds',
        icon: <ControlOutlined />,
        path: '/monitor/thresholds',
        permission: 'monitor:config'
      },
      {
        key: 'monitor-oid-tools',
        labelKey: 'menu.monitorOidTools',
        icon: <ReadOutlined />,
        path: '/monitor/oid-tools',
        permission: 'monitor:config'
      }
    ]
  },
  {
    key: 'ai',
    labelKey: 'menu.ai',
    icon: <RobotOutlined />,
    path: '/ai/nlq',
    permission: 'ai:use',
    children: [
      {
        key: 'ai-nlq',
        labelKey: 'menu.aiNlq',
        icon: <RobotOutlined />,
        path: '/ai/nlq',
        permission: 'ai:use'
      },
      {
        key: 'ai-skills',
        labelKey: 'menu.aiSkills',
        icon: <ApiOutlined />,
        path: '/ai/skills',
        permission: 'ai:admin'
      },
      {
        key: 'ai-config',
        labelKey: 'menu.aiConfig',
        icon: <SettingOutlined />,
        path: '/ai/config',
        permission: 'ai:admin'
      },
      {
        key: 'ai-monitor',
        labelKey: 'menu.aiMonitor',
        icon: <MonitorOutlined />,
        path: '/ai/monitor',
        permission: 'ai:admin'
      },
      {
        key: 'ai-audit',
        labelKey: 'menu.aiAudit',
        icon: <SafetyCertificateOutlined />,
        path: '/ai/audit',
        permission: 'ai:admin'
      },
      {
        key: 'ai-rag',
        labelKey: 'menu.aiRag',
        icon: <DatabaseOutlined />,
        path: '/ai/rag',
        permission: 'ai:use'
      },
      {
        key: 'ai-diagnosis',
        labelKey: 'menu.aiDiagnosis',
        icon: <MedicineBoxOutlined />,
        path: '/ai/diagnosis',
        permission: 'ai:agentic'
      }
    ]
  },
  {
    key: 'system',
    labelKey: 'menu.system',
    icon: <SettingOutlined />,
    path: '/users',
    permission: 'user:view',
    children: [
      {
        key: 'users',
        labelKey: 'menu.users',
        icon: <UserOutlined />,
        path: '/users',
        permission: 'user:view'
      },
      {
        key: 'rbac',
        labelKey: 'menu.rbac',
        icon: <SafetyOutlined />,
        path: '/rbac',
        permission: 'rbac:view'
      },
      {
        key: 'login-logs',
        labelKey: 'menu.loginLogs',
        icon: <FileSearchOutlined />,
        path: '/login-logs',
        permission: 'user:view'
      },
      {
        key: 'audit-logs',
        labelKey: 'menu.auditLogs',
        icon: <AuditOutlined />,
        path: '/audit-logs',
        permission: 'audit:view'
      },
      {
        key: 'notification-preferences',
        labelKey: 'menu.notificationPreferences',
        icon: <BellOutlined />,
        path: '/settings/notification-preferences'
      },
      {
        key: 'webhook-configs',
        labelKey: 'menu.webhookConfigs',
        icon: <ApiOutlined />,
        path: '/settings/webhook-configs',
        permission: 'user:view'
      },
      {
        key: 'mail-settings',
        labelKey: 'menu.mailSettings',
        icon: <MailOutlined />,
        path: '/settings/mail',
        permission: 'user:view'
      },
      {
        key: 'voice-settings',
        labelKey: 'menu.voiceSettings',
        icon: <PhoneOutlined />,
        path: '/settings/voice',
        permission: 'user:view'
      },
      {
        key: 'import-export',
        labelKey: 'menu.importExport',
        icon: <ImportOutlined />,
        path: '/import-export',
        permission: 'import:view'
      },
      {
        key: 'licenses',
        labelKey: 'menu.licenses',
        icon: <SafetyCertificateOutlined />,
        path: '/settings/licenses'
      }
    ]
  }
];

export const FLATTENED_MENUS: MenuConfig[] = MENU_CONFIGS.flatMap((m) =>
  m.children ? [m, ...m.children] : [m]
);

export const PATH_TO_MENU = new Map(FLATTENED_MENUS.map((m) => [m.path, m]));

/**
 * 根据路径查找匹配的菜单配置
 * 支持精确匹配和前缀匹配（如 /rooms/123 匹配 /rooms）
 */
export function findMenuByPath(pathname: string): MenuConfig | undefined {
  const exact = PATH_TO_MENU.get(pathname);
  if (exact) return exact;
  const segment = '/' + (pathname.split('/')[1] || '');
  return PATH_TO_MENU.get(segment);
}
