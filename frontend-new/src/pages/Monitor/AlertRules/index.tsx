/**
 * 监控中心 - 告警规则页（Tab 合并）
 *
 * 将原 静默规则 / 依赖抑制 / 升级策略 三个平铺页面合并为 Tab：
 * - ?tab=silence      静默规则（原 /monitor/silence-rules）
 * - ?tab=dependency   依赖抑制（原 /monitor/alert-dependency-rules）
 * - ?tab=escalation   升级策略（原 /monitor/escalation-policies）
 *
 * 三者均为告警治理规则的 CRUD 表格，UI 同构，统一入口降低运维认知负担。
 * 全部需要 monitor:config 权限，由外层 PermissionRoute 统一包裹。
 * Tab 状态用 URL query 持久化，刷新可恢复，支持外链直达。
 */
import { lazy, Suspense } from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';

const SilenceRules = lazy(() => import('@/pages/Monitor/SilenceRules'));
const AlertDependencyRules = lazy(() => import('@/pages/Monitor/AlertDependencyRules'));
const EscalationPolicies = lazy(() => import('@/pages/Monitor/EscalationPolicies'));

type AlertRuleTabKey = 'silence' | 'dependency' | 'escalation';
const DEFAULT_TAB: AlertRuleTabKey = 'silence';
const VALID_TABS: AlertRuleTabKey[] = ['silence', 'dependency', 'escalation'];

export default function AlertRules() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const activeKey: AlertRuleTabKey = VALID_TABS.includes(raw as AlertRuleTabKey)
    ? (raw as AlertRuleTabKey)
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
          key: 'silence',
          label: '静默规则',
          children: (
            <Suspense fallback={null}>
              <SilenceRules />
            </Suspense>
          )
        },
        {
          key: 'dependency',
          label: '依赖抑制',
          children: (
            <Suspense fallback={null}>
              <AlertDependencyRules />
            </Suspense>
          )
        },
        {
          key: 'escalation',
          label: '升级策略',
          children: (
            <Suspense fallback={null}>
              <EscalationPolicies />
            </Suspense>
          )
        }
      ]}
    />
  );
}
