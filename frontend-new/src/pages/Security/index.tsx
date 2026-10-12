import { Card, Space, Statistic, Tabs, Tag, Tooltip, Typography, theme } from 'antd';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import DataTable from '@/components/DataTable';
import {
  useSecurityFindings,
  useSecurityOverview,
  type OverviewItem,
  type SecurityFindingRow
} from '@/services/security';
import { severityColor } from '@/utils/statusColor';

import PolicyPanel from './PolicyPanel';
import RemoteLoginPanel from './RemoteLoginPanel';
import {
  SECURITY_RULE_LABEL_KEYS,
  SECURITY_SEVERITY_LABEL_KEYS,
  SECURITY_STATUS_LABEL_KEYS,
  type SecurityLabelKey
} from './labels';

const { Text } = Typography;

export default function SecurityCenter() {
  const { t } = useTranslation('security');
  const { token } = theme.useToken();
  const {
    data: overview,
    isLoading,
    error: overviewError,
    refetch: refetchOverview
  } = useSecurityOverview();
  const {
    data: findings,
    error: findingsError,
    refetch: refetchFindings
  } = useSecurityFindings({ status: 'open', per_page: 20 });

  const { overviewColumns, findingColumns } = useMemo(() => {
    const nameCell = (value: string, table: Record<string, SecurityLabelKey>) => {
      const key = table[value];
      return (
        <Tooltip title={value}>
          <Text>{key ? t(key) : value}</Text>
        </Tooltip>
      );
    };

    const ruleCell = (value: string) => nameCell(value, SECURITY_RULE_LABEL_KEYS);

    const severityCell = (value: string) => (
      <Tag color={severityColor(value, token) ?? token.colorTextSecondary}>
        {nameCell(value, SECURITY_SEVERITY_LABEL_KEYS)}
      </Tag>
    );

    const statusCell = (value: string) => (
      <Tag color={value === 'ok' ? token.colorSuccess : token.colorError}>
        {nameCell(value, SECURITY_STATUS_LABEL_KEYS)}
      </Tag>
    );

    return {
      overviewColumns: [
        { title: t('overview.rule'), dataIndex: 'rule_id', render: ruleCell },
        { title: t('overview.severity'), dataIndex: 'severity', render: severityCell },
        { title: t('overview.count'), dataIndex: 'violation_count' },
        { title: t('overview.status'), dataIndex: 'status', render: statusCell }
      ],
      findingColumns: [
        { title: t('overview.rule'), dataIndex: 'rule_id', render: ruleCell },
        { title: t('overview.severity'), dataIndex: 'severity', render: severityCell },
        { title: t('findings.subject'), dataIndex: 'subject_id' },
        { title: t('findings.lastSeen'), dataIndex: 'last_seen' }
      ]
    };
  }, [t, token]);

  return (
    <Card title={t('title')} loading={isLoading}>
      <Space size="large" wrap style={{ marginBottom: 16 }}>
        <Statistic
          title={t('overview.compliance')}
          value={`${overview?.compliance.ok ?? 0} / ${overview?.compliance.total ?? 0}`}
        />
        <Statistic title={t('overview.violations')} value={overview?.compliance.violated ?? 0} />
      </Space>
      <Tabs
        items={[
          {
            key: 'items',
            label: t('overview.tabItems'),
            children: (
              <DataTable<OverviewItem>
                columns={overviewColumns}
                dataSource={overview?.items ?? []}
                rowKey="rule_id"
                pagination={false}
                searchable={false}
                showCard={false}
                size="small"
                error={overviewError}
                onRetry={refetchOverview}
              />
            )
          },
          {
            key: 'findings',
            label: t('overview.tabFindings'),
            children: (
              <DataTable<SecurityFindingRow>
                columns={findingColumns}
                dataSource={findings?.items ?? []}
                rowKey="id"
                pagination={false}
                searchable={false}
                showCard={false}
                size="small"
                error={findingsError}
                onRetry={refetchFindings}
                emptyText={t('findings.empty')}
              />
            )
          },
          { key: 'policies', label: t('policies.title'), children: <PolicyPanel /> },
          { key: 'remote', label: t('remoteLogins.title'), children: <RemoteLoginPanel /> }
        ]}
      />
    </Card>
  );
}
