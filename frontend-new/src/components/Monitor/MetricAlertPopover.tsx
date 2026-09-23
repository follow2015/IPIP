import { Popover, Table, Tag, Spin, Empty } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useDeviceMetricAlerts } from '@/services/monitor';

type MetricAlertKey =
  | 'temperature'
  | 'port_updown'
  | 'disk_failure'
  | 'raid_failure'
  | 'monitor_interrupted';

const METRIC_KEY_LABEL = {
  temperature: 'alertPopover.metric.temperature',
  port_updown: 'alertPopover.metric.portUpdown',
  disk_failure: 'alertPopover.metric.diskFailure',
  raid_failure: 'alertPopover.metric.raidFailure',
  monitor_interrupted: 'alertPopover.metric.monitorInterrupted'
} as const;

const SEVERITY_COLOR: Record<string, string> = {
  crit: 'red',
  critical: 'red',
  warn: 'orange',
  warning: 'orange',
  info: 'blue',
  ok: 'green'
};

interface MetricAlertPopoverProps {
  deviceId: number;
  alertCount: number;
  maxSeverity: number;
}

export function MetricAlertPopover({ deviceId, alertCount, maxSeverity }: MetricAlertPopoverProps) {
  const { t } = useTranslation('monitor');
  const { data, isLoading } = useDeviceMetricAlerts(deviceId);

  if (alertCount === 0) {
    return <span style={{ color: '#999' }}>{t('alertPopover.normal')}</span>;
  }

  const color = maxSeverity >= 3 ? 'magenta' : 'volcano';

  const content = isLoading ? (
    <Spin size="small" />
  ) : !data?.items?.length ? (
    <Empty description={t('alertPopover.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
  ) : (
    <Table
      dataSource={data.items}
      rowKey="id"
      size="small"
      pagination={false}
      style={{ minWidth: 360 }}
      columns={[
        {
          title: t('alertPopover.column.metric'),
          dataIndex: 'metric_key',
          width: 90,
          render: (key: string) => {
            const labelKey = METRIC_KEY_LABEL[key as MetricAlertKey];
            return labelKey ? t(labelKey) : key;
          }
        },
        {
          title: t('alertPopover.column.instance'),
          dataIndex: 'index_key',
          width: 120,
          render: (v: string) => v || '—',
          ellipsis: true
        },
        {
          title: t('alertPopover.column.severity'),
          dataIndex: 'severity',
          width: 70,
          render: (sev: string | null) => (
            <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>{sev ?? '—'}</Tag>
          )
        },
        {
          title: t('alertPopover.column.value'),
          dataIndex: 'last_value',
          width: 80,
          render: (v: string | null) => v ?? '—'
        }
      ]}
      scroll={{ x: 'max-content' }}
    />
  );

  return (
    <Popover title={t('alertPopover.title')} content={content} trigger="click" placement="left">
      <Tag color={color} icon={<WarningOutlined />} style={{ cursor: 'pointer' }}>
        {t('alertPopover.count', { count: alertCount })}
      </Tag>
    </Popover>
  );
}

export default MetricAlertPopover;
