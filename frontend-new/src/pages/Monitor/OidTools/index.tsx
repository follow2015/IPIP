/**
 * 监控中心 - OID 工具箱页（Tab 合并）
 *
 * 将原 MIB 探测 / OID 规则 两个平铺页面合并为 Tab：
 * - ?tab=mib        MIB 探测（原 /monitor/mib-scan）
 * - ?tab=oid-rules  OID 规则（原 /monitor/oid-rule-config）
 *
 * 探测→分类是 OID 治理闭环，合并后流程更连贯。
 * 全部需要 monitor:config 权限，由外层 PermissionRoute 统一包裹。
 * Tab 状态用 URL query 持久化，刷新可恢复，支持外链直达。
 */
import { lazy, Suspense } from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';

const MibScan = lazy(() => import('@/pages/Monitor/MibScan'));
const OidRuleConfig = lazy(() => import('@/pages/Monitor/OidRuleConfig'));

type OidTabKey = 'mib' | 'oid-rules';
const DEFAULT_TAB: OidTabKey = 'mib';
const VALID_TABS: OidTabKey[] = ['mib', 'oid-rules'];

export default function OidTools() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const activeKey: OidTabKey = VALID_TABS.includes(raw as OidTabKey)
    ? (raw as OidTabKey)
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
          key: 'mib',
          label: 'MIB 探测',
          children: (
            <Suspense fallback={null}>
              <MibScan />
            </Suspense>
          )
        },
        {
          key: 'oid-rules',
          label: 'OID 规则',
          children: (
            <Suspense fallback={null}>
              <OidRuleConfig />
            </Suspense>
          )
        }
      ]}
    />
  );
}
