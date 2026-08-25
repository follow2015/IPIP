/**
 * 监控中心 - 阈值与目标页（Tab 合并）
 *
 * 将原 指标模板 / 设备覆盖 / SLA-SLO 三个平铺页面合并为 Tab：
 * - ?tab=templates   指标模板（原 /monitor/metric-templates，config 权限）
 * - ?tab=overrides   设备覆盖（原 /monitor/threshold-overrides，config 权限）
 * - ?tab=sla         SLA/SLO（原 /monitor/sla-targets，view 权限）
 *
 * 三者构成"全局模板 → 设备覆盖 → SLA 目标"的递进关系，Tab 顺序即语义。
 * 外层 PermissionRoute 用 monitor:config（覆盖 templates/overrides），
 * SLA Tab 内嵌 PermissionRoute monitor:view 放宽权限，使仅 view 权限用户也能查看 SLA。
 * Tab 状态用 URL query 持久化，刷新可恢复，支持外链直达。
 */
import { lazy, Suspense } from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { PermissionRoute } from '@/router/guards';

const MetricTemplates = lazy(() => import('@/pages/Monitor/MetricTemplates'));
const ThresholdOverrides = lazy(() => import('@/pages/Monitor/ThresholdOverrides'));
const SlaTargets = lazy(() => import('@/pages/Monitor/SlaTargets'));

type ThresholdTabKey = 'templates' | 'overrides' | 'sla';
const DEFAULT_TAB: ThresholdTabKey = 'templates';
const VALID_TABS: ThresholdTabKey[] = ['templates', 'overrides', 'sla'];

export default function Thresholds() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const activeKey: ThresholdTabKey = VALID_TABS.includes(raw as ThresholdTabKey)
    ? (raw as ThresholdTabKey)
    : DEFAULT_TAB;

  const handleChange = (key: string) => {
    setParams({ tab: key }, { replace: true });
  };

  return (
    <Tabs
      activeKey={activeKey}
      onChange={handleChange}
      destroyInactiveTabPane={false}
      items={[
        {
          key: 'templates',
          label: '指标模板',
          children: (
            <Suspense fallback={null}>
              <MetricTemplates />
            </Suspense>
          )
        },
        {
          key: 'overrides',
          label: '设备覆盖',
          children: (
            <Suspense fallback={null}>
              <ThresholdOverrides />
            </Suspense>
          )
        },
        {
          key: 'sla',
          label: 'SLA/SLO',
          children: (
            <PermissionRoute requiredPermission="monitor:view">
              <Suspense fallback={null}>
                <SlaTargets />
              </Suspense>
            </PermissionRoute>
          )
        }
      ]}
    />
  );
}
