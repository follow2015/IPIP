/**
 * 监控中心 - 告警中心页（Tab 合并）
 *
 * 重构（M29）：
 * - NOC 大屏 Tab 激活时隐藏外层 Tab 栏，全屏沉浸投屏
 * - Tab 栏改为紧凑样式，左侧标签 + 右侧操作区
 * - Tab 状态用 URL query 持久化，刷新可恢复，支持外链直达
 *
 * 三者数据源相同（useMonitorAlerts + useAlertStatistics），Tab 切换零额外请求。
 */
import { lazy, Suspense, useState, useEffect } from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';

const MonitorAlerts = lazy(() => import('@/pages/Monitor/Alerts'));
const MonitorReports = lazy(() => import('@/pages/Monitor/Reports'));
const MonitorNocScreen = lazy(() => import('@/pages/Monitor/NocScreen'));

type AlertTabKey = 'list' | 'reports' | 'noc';
const DEFAULT_TAB: AlertTabKey = 'list';
const VALID_TABS: AlertTabKey[] = ['list', 'reports', 'noc'];

export default function AlertCenter() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const activeKey: AlertTabKey = VALID_TABS.includes(raw as AlertTabKey)
    ? (raw as AlertTabKey)
    : DEFAULT_TAB;

  const [isFullscreen, setIsFullscreen] = useState(false);
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const handleChange = (key: string) => {
    setParams({ tab: key }, { replace: true });
  };

  const hideTabBar = activeKey === 'noc' && isFullscreen;

  if (hideTabBar) {
    return (
      <Suspense fallback={null}>
        <MonitorNocScreen />
      </Suspense>
    );
  }

  return (
    <Tabs
      activeKey={activeKey}
      onChange={handleChange}
      destroyInactiveTabPane={false}
      size="large"
      tabBarStyle={{ marginBottom: 16, paddingLeft: 4 }}
      items={[
        {
          key: 'list',
          label: '告警列表',
          children: (
            <Suspense fallback={null}>
              <MonitorAlerts />
            </Suspense>
          )
        },
        {
          key: 'reports',
          label: '统计报表',
          children: (
            <Suspense fallback={null}>
              <MonitorReports />
            </Suspense>
          )
        },
        {
          key: 'noc',
          label: 'NOC 大屏',
          children: (
            <Suspense fallback={null}>
              <MonitorNocScreen />
            </Suspense>
          )
        }
      ]}
    />
  );
}
