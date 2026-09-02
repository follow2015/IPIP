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

export interface MenuConfig {
  key: string;
  label: string;
  icon: React.ReactNode;
  path: string;
  permission?: string;
  children?: MenuConfig[];
}

export const MENU_CONFIGS: MenuConfig[] = [
  { key: 'dashboard', label: '仪表盘', icon: <DashboardOutlined />, path: '/dashboard' },
  {
    key: 'asset',
    label: '资产管理',
    icon: <HomeOutlined />,
    path: '/rooms',
    permission: 'room:view',
    children: [
      {
        key: 'rooms',
        label: '机房管理',
        icon: <HomeOutlined />,
        path: '/rooms',
        permission: 'room:view'
      },
      {
        key: 'cabinets',
        label: '机柜管理',
        icon: <DatabaseOutlined />,
        path: '/cabinets',
        permission: 'cabinet:view'
      },
      {
        key: 'devices',
        label: '设备管理',
        icon: <CloudServerOutlined />,
        path: '/devices',
        permission: 'device:view'
      },
      {
        key: 'device-recycle-bin',
        label: '设备回收站',
        icon: <DeleteOutlined />,
        path: '/device-recycle-bin',
        permission: 'device:view'
      },
      {
        key: 'customers',
        label: '客户管理',
        icon: <TeamOutlined />,
        path: '/customers',
        permission: 'customer:view'
      },
      {
        key: 'component-templates',
        label: '配件模板管理',
        icon: <AppstoreOutlined />,
        path: '/settings/component-templates',
        permission: 'customer:view'
      },
      {
        key: 'vendor-brands',
        label: '厂商品牌',
        icon: <SafetyOutlined />,
        path: '/asset/vendor-brands',
        permission: 'monitor:config'
      }
    ]
  },
  {
    key: 'network-group',
    label: '网络管理',
    icon: <ApartmentOutlined />,
    path: '/ip',
    permission: 'ip:view',
    children: [
      {
        key: 'ip',
        label: 'IP管理',
        icon: <GlobalOutlined />,
        path: '/ip',
        permission: 'ip:view'
      },
      {
        key: 'switches',
        label: '网络设备管理',
        icon: <SwapOutlined />,
        path: '/switches',
        permission: 'switch:view'
      },
      {
        key: 'network',
        label: '网段管理',
        icon: <ApartmentOutlined />,
        path: '/network',
        permission: 'network:view'
      },
      {
        key: 'vlans',
        label: 'VLAN管理',
        icon: <PartitionOutlined />,
        path: '/vlans',
        permission: 'switch:view'
      },
      {
        key: 'link-aggregations',
        label: '链路聚合',
        icon: <GroupOutlined />,
        path: '/link-aggregations',
        permission: 'switch:view'
      },
      {
        key: 'topology',
        label: '网络拓扑',
        icon: <DeploymentUnitOutlined />,
        path: '/topology',
        permission: 'switch:view'
      },
      {
        key: 'virtual-rooms',
        label: '虚拟机房',
        icon: <ClusterOutlined />,
        path: '/virtual-rooms',
        permission: 'switch:view'
      }
    ]
  },
  {
    key: 'monitor',
    label: '监控中心',
    icon: <MonitorOutlined />,
    path: '/monitor',
    permission: 'monitor:view',
    children: [
      {
        key: 'monitor-overview',
        label: '总览',
        icon: <MonitorOutlined />,
        path: '/monitor/overview',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-alerts',
        label: '告警中心',
        icon: <BellOutlined />,
        path: '/monitor/alerts',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-incidents',
        label: '事件中心',
        icon: <ThunderboltOutlined />,
        path: '/monitor/incidents',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-history',
        label: '历史趋势',
        icon: <LineChartOutlined />,
        path: '/monitor/history',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-credentials',
        label: '凭据管理',
        icon: <SafetyOutlined />,
        path: '/monitor/credentials',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-settings',
        label: '运行配置',
        icon: <ApiOutlined />,
        path: '/monitor/settings',
        permission: 'monitor:view'
      },
      {
        key: 'monitor-alert-rules',
        label: '告警规则',
        icon: <AlertOutlined />,
        path: '/monitor/alert-rules',
        permission: 'monitor:config'
      },
      {
        key: 'monitor-thresholds',
        label: '阈值与目标',
        icon: <ControlOutlined />,
        path: '/monitor/thresholds',
        permission: 'monitor:config'
      },
      {
        key: 'monitor-oid-tools',
        label: 'OID 工具箱',
        icon: <ReadOutlined />,
        path: '/monitor/oid-tools',
        permission: 'monitor:config'
      }
    ]
  },
  {
    key: 'ai',
    label: 'AI 助手',
    icon: <RobotOutlined />,
    path: '/ai/nlq',
    permission: 'ai:use',
    children: [
      {
        key: 'ai-nlq',
        label: '智能查询',
        icon: <RobotOutlined />,
        path: '/ai/nlq',
        permission: 'ai:use'
      },
      {
        key: 'ai-skills',
        label: '技能管理',
        icon: <ApiOutlined />,
        path: '/ai/skills',
        permission: 'ai:admin'
      },
      {
        key: 'ai-config',
        label: 'AI 配置',
        icon: <SettingOutlined />,
        path: '/ai/config',
        permission: 'ai:admin'
      },
      {
        key: 'ai-monitor',
        label: '运行监控',
        icon: <MonitorOutlined />,
        path: '/ai/monitor',
        permission: 'ai:admin'
      },
      {
        key: 'ai-audit',
        label: '审计日志',
        icon: <SafetyCertificateOutlined />,
        path: '/ai/audit',
        permission: 'ai:admin'
      },
      {
        key: 'ai-rag',
        label: '知识库',
        icon: <DatabaseOutlined />,
        path: '/ai/rag',
        permission: 'ai:use'
      },
      {
        key: 'ai-diagnosis',
        label: '智能诊断',
        icon: <MedicineBoxOutlined />,
        path: '/ai/diagnosis',
        permission: 'ai:agentic'
      }
    ]
  },
  {
    key: 'system',
    label: '系统管理',
    icon: <SettingOutlined />,
    path: '/users',
    permission: 'user:view',
    children: [
      {
        key: 'users',
        label: '用户管理',
        icon: <UserOutlined />,
        path: '/users',
        permission: 'user:view'
      },
      {
        key: 'rbac',
        label: '角色管理',
        icon: <SafetyOutlined />,
        path: '/rbac',
        permission: 'rbac:view'
      },
      {
        key: 'login-logs',
        label: '日志管理',
        icon: <FileSearchOutlined />,
        path: '/login-logs',
        permission: 'user:view'
      },
      {
        key: 'audit-logs',
        label: '审计日志',
        icon: <AuditOutlined />,
        path: '/audit-logs',
        permission: 'audit:view'
      },
      {
        key: 'notification-preferences',
        label: '通知偏好',
        icon: <BellOutlined />,
        path: '/settings/notification-preferences'
      },
      {
        key: 'webhook-configs',
        label: 'Webhook配置',
        icon: <ApiOutlined />,
        path: '/settings/webhook-configs',
        permission: 'user:view'
      },
      {
        key: 'mail-settings',
        label: '邮件配置',
        icon: <MailOutlined />,
        path: '/settings/mail',
        permission: 'user:view'
      },
      {
        key: 'voice-settings',
        label: '语音配置',
        icon: <PhoneOutlined />,
        path: '/settings/voice',
        permission: 'user:view'
      },
      {
        key: 'import-export',
        label: '导入导出',
        icon: <ImportOutlined />,
        path: '/import-export',
        permission: 'import:view'
      },
      {
        key: 'licenses',
        label: '开源授权',
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
