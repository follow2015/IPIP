/**
 * 路由定义
 * - 所有页面使用 React.lazy 懒加载
 * - 嵌套在 AppLayout 下
 */
import React, { Suspense } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';
import { PrivateRoute, PermissionRoute } from './guards';
import PageLoading from '@/components/PageLoading';
import ErrorBoundary from '@/components/ErrorBoundary';
import AppLayout from '@/components/Layout/AppLayout';


const Login = React.lazy(() => import('@/pages/Login'));
const Dashboard = React.lazy(() => import('@/pages/Dashboard'));
const Rooms = React.lazy(() => import('@/pages/Rooms'));
const RoomDetail = React.lazy(() => import('@/pages/Rooms/RoomDetail'));
const Cabinets = React.lazy(() => import('@/pages/Cabinets'));
const CabinetDetail = React.lazy(() => import('@/pages/Cabinets/CabinetDetail'));
const Devices = React.lazy(() => import('@/pages/Devices'));
const DeviceDetail = React.lazy(() => import('@/pages/Devices/DeviceDetail'));
const IP = React.lazy(() => import('@/pages/IP'));
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
const Licenses = React.lazy(() => import('@/pages/Settings/Licenses'));
const DeviceRecycleBin = React.lazy(() => import('@/pages/DeviceRecycleBin'));
const Topology = React.lazy(() => import('@/pages/Topology'));
const VirtualRooms = React.lazy(() => import('@/pages/VirtualRooms'));
const MonitorOverview = React.lazy(() => import('@/pages/Monitor/Overview'));
const MonitorCredentials = React.lazy(() => import('@/pages/Monitor/Credentials'));
const MonitorSettings = React.lazy(() => import('@/pages/Monitor/Settings'));
const MonitorHistory = React.lazy(() => import('@/pages/Monitor/History'));

const MonitorAlertCenter = React.lazy(() => import('@/pages/Monitor/AlertCenter'));
const MonitorAlertRules = React.lazy(() => import('@/pages/Monitor/AlertRules'));
const MonitorThresholds = React.lazy(() => import('@/pages/Monitor/Thresholds'));
const MonitorOidTools = React.lazy(() => import('@/pages/Monitor/OidTools'));

const MonitorNocScreenFullscreen = React.lazy(() => import('@/pages/Monitor/NocScreen'));
const VendorBrandsPage = React.lazy(() => import('@/pages/Asset/VendorBrands'));
const NotFound = React.lazy(() => import('@/pages/NotFound'));


const withSuspense = (Component: React.LazyExoticComponent<React.ComponentType>) => (
  <ErrorBoundary>
    <Suspense fallback={<PageLoading />}>
      <Component />
    </Suspense>
  </ErrorBoundary>
);


export const routes: RouteObject[] = [
  {
    path: '/login',
    element: withSuspense(Login)
  },
  {
    
    path: '/monitor/noc-screen/fullscreen',
    element: <PrivateRoute>{withSuspense(MonitorNocScreenFullscreen)}</PrivateRoute>
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
      { path: 'dashboard', element: withSuspense(Dashboard) },
      { path: 'rooms', element: withSuspense(Rooms) },
      { path: 'rooms/:id', element: withSuspense(RoomDetail) },
      { path: 'cabinets', element: withSuspense(Cabinets) },
      { path: 'cabinets/:id', element: withSuspense(CabinetDetail) },
      { path: 'devices', element: withSuspense(Devices) },
      { path: 'devices/:id', element: withSuspense(DeviceDetail) },
      {
        path: 'device-recycle-bin',
        element: (
          <PermissionRoute requiredPermission="device:view">
            {withSuspense(DeviceRecycleBin)}
          </PermissionRoute>
        )
      },
      { path: 'ip', element: withSuspense(IP) },
      { path: 'switches', element: withSuspense(Switches) },
      { path: 'switches/:id', element: withSuspense(SwitchDetail) },
      { path: 'network', element: withSuspense(Network) },
      { path: 'network/:ipNetwork', element: withSuspense(NetworkDetail) },
      { path: 'import-export', element: withSuspense(ImportExport) },
      { path: 'customers', element: withSuspense(Customers) },
      { path: 'customers/:id', element: withSuspense(CustomerDetail) },
      {
        path: 'users',
        element: (
          <PermissionRoute requiredPermission="user:view">{withSuspense(Users)}</PermissionRoute>
        )
      },
      { path: 'profile', element: withSuspense(Profile) },
      {
        path: 'rbac',
        element: (
          <PermissionRoute requiredPermission="rbac:view">{withSuspense(RBAC)}</PermissionRoute>
        )
      },
      { path: 'login-logs', element: withSuspense(LoginLogs) },
      { path: 'vlans', element: withSuspense(VLANsPage) },
      { path: 'link-aggregations', element: withSuspense(LinkAggregationsPage) },
      { path: 'topology', element: withSuspense(Topology) },
      { path: 'virtual-rooms', element: withSuspense(VirtualRooms) },
      { path: 'monitor', element: <Navigate to="/monitor/overview" replace /> },
      {
        path: 'monitor/overview',
        element: (
          <PermissionRoute requiredPermission="monitor:view">
            {withSuspense(MonitorOverview)}
          </PermissionRoute>
        )
      },
      {
        path: 'monitor/credentials',
        element: (
          <PermissionRoute requiredPermission="monitor:view">
            {withSuspense(MonitorCredentials)}
          </PermissionRoute>
        )
      },
      {
        path: 'monitor/settings',
        element: (
          <PermissionRoute requiredPermission="monitor:view">
            {withSuspense(MonitorSettings)}
          </PermissionRoute>
        )
      },
      {
        path: 'monitor/alerts',
        element: (
          <PermissionRoute requiredPermission="monitor:view">
            {withSuspense(MonitorAlertCenter)}
          </PermissionRoute>
        )
      },
      
      { path: 'monitor/reports', element: <Navigate to="/monitor/alerts?tab=reports" replace /> },
      { path: 'monitor/noc-screen', element: <Navigate to="/monitor/alerts?tab=noc" replace /> },
      {
        path: 'monitor/history',
        element: (
          <PermissionRoute requiredPermission="monitor:view">
            {withSuspense(MonitorHistory)}
          </PermissionRoute>
        )
      },
      {
        path: 'monitor/alert-rules',
        element: (
          <PermissionRoute requiredPermission="monitor:config">
            {withSuspense(MonitorAlertRules)}
          </PermissionRoute>
        )
      },
      
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
      {
        path: 'monitor/thresholds',
        element: (
          <PermissionRoute requiredPermission="monitor:config">
            {withSuspense(MonitorThresholds)}
          </PermissionRoute>
        )
      },
      
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
      {
        path: 'monitor/oid-tools',
        element: (
          <PermissionRoute requiredPermission="monitor:config">
            {withSuspense(MonitorOidTools)}
          </PermissionRoute>
        )
      },
      
      { path: 'monitor/mib-scan', element: <Navigate to="/monitor/oid-tools?tab=mib" replace /> },
      {
        path: 'monitor/oid-rule-config',
        element: <Navigate to="/monitor/oid-tools?tab=oid-rules" replace />
      },
      { path: 'audit-logs', element: withSuspense(AuditLogsPage) },
      {
        path: 'asset/vendor-brands',
        element: (
          <PermissionRoute requiredPermission="monitor:config">
            {withSuspense(VendorBrandsPage)}
          </PermissionRoute>
        )
      },
      { path: 'settings/component-templates', element: withSuspense(ComponentTemplateManager) },
      {
        path: 'settings/notification-preferences',
        element: withSuspense(NotificationPreferencesPage)
      },
      {
        path: 'settings/webhook-configs',
        element: (
          <PermissionRoute requiredPermission="user:view">
            {withSuspense(WebhookConfigManagement)}
          </PermissionRoute>
        )
      },
      {
        path: 'settings/mail',
        element: (
          <PermissionRoute requiredPermission="user:view">
            {withSuspense(MailSettings)}
          </PermissionRoute>
        )
      },
      {
        path: 'settings/licenses',
        element: withSuspense(Licenses)
      },
      { path: '*', element: withSuspense(NotFound) }
    ]
  }
];
