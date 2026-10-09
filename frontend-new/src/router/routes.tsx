/**
 * 路由定义
 * - 所有页面使用 React.lazy 懒加载
 * - 嵌套在 AppLayout 下
 */
import React, { Suspense } from 'react';
import { Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';
import { PrivateRoute, PermissionRoute } from './guards';
import { ROUTE_PERMISSIONS } from './routePermissions';
import PageLoading from '@/components/PageLoading';
import ErrorBoundary from '@/components/ErrorBoundary';
import AppLayout from '@/components/Layout/AppLayout';

const Login = React.lazy(() => import('@/pages/Login'));
const Dashboard = React.lazy(() => import('@/pages/Dashboard'));
const Rooms = React.lazy(() => import('@/pages/Rooms'));
const RoomDetail = React.lazy(() => import('@/pages/Rooms/RoomDetail'));
const RoomOverview = React.lazy(() => import('@/pages/Rooms/RoomOverview'));
const Cabinets = React.lazy(() => import('@/pages/Cabinets'));
const CabinetDetail = React.lazy(() => import('@/pages/Cabinets/CabinetDetail'));
const Devices = React.lazy(() => import('@/pages/Devices'));
const DeviceDetail = React.lazy(() => import('@/pages/Devices/DeviceDetail'));
const IP = React.lazy(() => import('@/pages/IP'));
const IPAudit = React.lazy(() => import('@/pages/IP/IPAudit'));
const Switches = React.lazy(() => import('@/pages/Switches'));
const SwitchDetail = React.lazy(() => import('@/pages/Switches/SwitchDetail'));
const Network = React.lazy(() => import('@/pages/Network'));
const NetworkDetail = React.lazy(() => import('@/pages/Network/NetworkDetail'));
const ImportExport = React.lazy(() => import('@/pages/ImportExport'));
const Customers = React.lazy(() => import('@/pages/Customers'));
const CustomerDetail = React.lazy(() => import('@/pages/Customers/CustomerDetail'));
const Users = React.lazy(() => import('@/pages/Users'));
const Profile = React.lazy(() => import('@/pages/Profile'));
const RBAC = React.lazy(() => import('@/pages/RBAC'));
const LoginLogs = React.lazy(() => import('@/pages/LoginLogs'));
const VLANsPage = React.lazy(() => import('@/pages/VLANs'));
const LinkAggregationsPage = React.lazy(() => import('@/pages/LinkAggregations'));
const AuditLogsPage = React.lazy(() => import('@/pages/AuditLogs'));
const ComponentTemplateManager = React.lazy(
  () => import('@/pages/Settings/ComponentTemplateManager')
);
const NotificationPreferencesPage = React.lazy(
  () => import('@/pages/Settings/NotificationPreferences')
);
const WebhookConfigManagement = React.lazy(
  () => import('@/pages/Settings/WebhookConfigManagement')
);
const MailSettings = React.lazy(() => import('@/pages/Settings/MailSettings'));
const VoiceSettings = React.lazy(() => import('@/pages/Settings/VoiceSettings'));
const Licenses = React.lazy(() => import('@/pages/Settings/Licenses'));
const DeviceRecycleBin = React.lazy(() => import('@/pages/DeviceRecycleBin'));
const Topology = React.lazy(() => import('@/pages/Topology'));
const VirtualRooms = React.lazy(() => import('@/pages/VirtualRooms'));
const MonitorOverview = React.lazy(() => import('@/pages/Monitor/Overview'));
const MonitorCredentials = React.lazy(() => import('@/pages/Monitor/Credentials'));
const MonitorSettings = React.lazy(() => import('@/pages/Monitor/Settings'));
const MonitorHistory = React.lazy(() => import('@/pages/Monitor/History'));
const MonitorAlertCenter = React.lazy(() => import('@/pages/Monitor/AlertCenter'));
const MonitorIncidents = React.lazy(() => import('@/pages/Monitor/Incidents'));
const MonitorAlertRules = React.lazy(() => import('@/pages/Monitor/AlertRules'));
const MonitorThresholds = React.lazy(() => import('@/pages/Monitor/Thresholds'));
const MonitorOidTools = React.lazy(() => import('@/pages/Monitor/OidTools'));
const MonitorNocScreenFullscreen = React.lazy(() => import('@/pages/Monitor/NocScreen'));
const AIPage = React.lazy(() => import('@/pages/AI'));
const AISkillsPage = React.lazy(() => import('@/pages/AI/Skills'));
const AIConfigPage = React.lazy(() => import('@/pages/AI/AIConfig'));
const AIMonitorPage = React.lazy(() => import('@/pages/AI/AIMonitor'));
const AIAuditPage = React.lazy(() => import('@/pages/AI/AIAudit'));
const AIRAGPage = React.lazy(() => import('@/pages/AI/RAG'));
const AIDiagnosisPage = React.lazy(() => import('@/pages/AIDiagnosis'));
const VendorBrandsPage = React.lazy(() => import('@/pages/Asset/VendorBrands'));
const CarriersPage = React.lazy(() => import('@/pages/Carriers'));
const CircuitsPage = React.lazy(() => import('@/pages/Circuits'));
const NotFound = React.lazy(() => import('@/pages/NotFound'));

const withSuspense = (Component: React.LazyExoticComponent<React.ComponentType>) => (
  <ErrorBoundary>
    <Suspense fallback={<PageLoading />}>
      <Component />
    </Suspense>
  </ErrorBoundary>
);

const guarded = (
  routePath: string,
  Component: React.LazyExoticComponent<React.ComponentType>
): React.ReactNode => {
  const page = withSuspense(Component);
  const requiredPermission = ROUTE_PERMISSIONS[routePath];
  if (!requiredPermission) return page;
  return <PermissionRoute requiredPermission={requiredPermission}>{page}</PermissionRoute>;
};

export const routes: RouteObject[] = [
  {
    path: '/login',
    element: withSuspense(Login)
  },
  {
    path: '/monitor/noc-screen/fullscreen',
    element: (
      <PrivateRoute>
        {guarded('/monitor/noc-screen/fullscreen', MonitorNocScreenFullscreen)}
      </PrivateRoute>
    )
  },
  {
    path: '/',
    element: (
      <PrivateRoute>
        <AppLayout />
      </PrivateRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: guarded('dashboard', Dashboard) },
      { path: 'rooms', element: guarded('rooms', Rooms) },
      { path: 'rooms/overview', element: guarded('rooms/overview', RoomOverview) },
      { path: 'rooms/:id', element: guarded('rooms/:id', RoomDetail) },
      { path: 'cabinets', element: guarded('cabinets', Cabinets) },
      { path: 'cabinets/:id', element: guarded('cabinets/:id', CabinetDetail) },
      { path: 'devices', element: guarded('devices', Devices) },
      { path: 'devices/:id', element: guarded('devices/:id', DeviceDetail) },
      { path: 'device-recycle-bin', element: guarded('device-recycle-bin', DeviceRecycleBin) },
      { path: 'ip', element: guarded('ip', IP) },
      { path: 'ip/audit', element: guarded('ip/audit', IPAudit) },
      { path: 'switches', element: guarded('switches', Switches) },
      { path: 'switches/:id', element: guarded('switches/:id', SwitchDetail) },
      { path: 'network', element: guarded('network', Network) },
      { path: 'network/:ipNetwork', element: guarded('network/:ipNetwork', NetworkDetail) },
      { path: 'import-export', element: guarded('import-export', ImportExport) },
      { path: 'customers', element: guarded('customers', Customers) },
      { path: 'customers/:id', element: guarded('customers/:id', CustomerDetail) },
      { path: 'carriers', element: guarded('carriers', CarriersPage) },
      { path: 'circuits', element: guarded('circuits', CircuitsPage) },
      { path: 'users', element: guarded('users', Users) },
      { path: 'profile', element: guarded('profile', Profile) },
      { path: 'rbac', element: guarded('rbac', RBAC) },
      { path: 'login-logs', element: guarded('login-logs', LoginLogs) },
      { path: 'vlans', element: guarded('vlans', VLANsPage) },
      { path: 'link-aggregations', element: guarded('link-aggregations', LinkAggregationsPage) },
      { path: 'topology', element: guarded('topology', Topology) },
      { path: 'virtual-rooms', element: guarded('virtual-rooms', VirtualRooms) },
      { path: 'monitor', element: <Navigate to="/monitor/overview" replace /> },
      { path: 'monitor/overview', element: guarded('monitor/overview', MonitorOverview) },
      { path: 'monitor/credentials', element: guarded('monitor/credentials', MonitorCredentials) },
      { path: 'monitor/settings', element: guarded('monitor/settings', MonitorSettings) },
      { path: 'monitor/alerts', element: guarded('monitor/alerts', MonitorAlertCenter) },
      { path: 'monitor/incidents', element: guarded('monitor/incidents', MonitorIncidents) },
      { path: 'monitor/reports', element: <Navigate to="/monitor/alerts?tab=reports" replace /> },
      { path: 'monitor/noc-screen', element: <Navigate to="/monitor/alerts?tab=noc" replace /> },
      { path: 'monitor/history', element: guarded('monitor/history', MonitorHistory) },
      { path: 'monitor/alert-rules', element: guarded('monitor/alert-rules', MonitorAlertRules) },
      {
        path: 'monitor/silence-rules',
        element: <Navigate to="/monitor/alert-rules?tab=silence" replace />
      },
      {
        path: 'monitor/alert-dependency-rules',
        element: <Navigate to="/monitor/alert-rules?tab=dependency" replace />
      },
      {
        path: 'monitor/escalation-policies',
        element: <Navigate to="/monitor/alert-rules?tab=escalation" replace />
      },
      { path: 'monitor/thresholds', element: guarded('monitor/thresholds', MonitorThresholds) },
      {
        path: 'monitor/metric-templates',
        element: <Navigate to="/monitor/thresholds?tab=templates" replace />
      },
      {
        path: 'monitor/threshold-overrides',
        element: <Navigate to="/monitor/thresholds?tab=overrides" replace />
      },
      {
        path: 'monitor/sla-targets',
        element: <Navigate to="/monitor/thresholds?tab=sla" replace />
      },
      { path: 'monitor/oid-tools', element: guarded('monitor/oid-tools', MonitorOidTools) },
      { path: 'monitor/mib-scan', element: <Navigate to="/monitor/oid-tools?tab=mib" replace /> },
      {
        path: 'monitor/oid-rule-config',
        element: <Navigate to="/monitor/oid-tools?tab=oid-rules" replace />
      },
      { path: 'ai', element: <Navigate to="/ai/nlq" replace /> },
      { path: 'ai/nlq', element: guarded('ai/nlq', AIPage) },
      { path: 'ai/skills', element: guarded('ai/skills', AISkillsPage) },
      { path: 'ai/config', element: guarded('ai/config', AIConfigPage) },
      { path: 'ai/monitor', element: guarded('ai/monitor', AIMonitorPage) },
      { path: 'ai/audit', element: guarded('ai/audit', AIAuditPage) },
      { path: 'ai/rag', element: guarded('ai/rag', AIRAGPage) },
      { path: 'ai/diagnosis', element: guarded('ai/diagnosis', AIDiagnosisPage) },
      { path: 'audit-logs', element: guarded('audit-logs', AuditLogsPage) },
      { path: 'asset/vendor-brands', element: guarded('asset/vendor-brands', VendorBrandsPage) },
      {
        path: 'settings/component-templates',
        element: guarded('settings/component-templates', ComponentTemplateManager)
      },
      {
        path: 'settings/notification-preferences',
        element: guarded('settings/notification-preferences', NotificationPreferencesPage)
      },
      {
        path: 'settings/webhook-configs',
        element: guarded('settings/webhook-configs', WebhookConfigManagement)
      },
      { path: 'settings/mail', element: guarded('settings/mail', MailSettings) },
      { path: 'settings/voice', element: guarded('settings/voice', VoiceSettings) },
      { path: 'settings/licenses', element: guarded('settings/licenses', Licenses) },
      { path: '*', element: guarded('*', NotFound) }
    ]
  }
];
