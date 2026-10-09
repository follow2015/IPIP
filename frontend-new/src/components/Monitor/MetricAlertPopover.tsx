import { useMemo } from 'react';
import { Popover, Table, Tag, Spin, Empty, theme } from 'antd';
import { severityColor } from '@/utils/statusColor';
import { WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TableProps } from 'antd';
import { useDeviceMetricAlerts, type DeviceMetricAlertItem } from '@/services/monitor';

type MetricAlertKey =
  'temperature' | 'port_updown' | 'disk_failure' | 'raid_failure' | 'monitor_interrupted';

const METRIC_KEY_LABEL = {
  temperature: 'alertPopover.metric.temperature',
  port_updown: 'alertPopover.metric.portUpdown',
  disk_failure: 'alertPopover.metric.diskFailure',
  raid_failure: 'alertPopover.metric.raidFailure',
  monitor_interrupted: 'alertPopover.metric.monitorInterrupted'
} as const;


interface MetricAlertPopoverProps {
  deviceId: number;
  alertCount: number;
  maxSeverity: number;
}

export function MetricAlertPopover({ deviceId, alertCount, maxSeverity }: MetricAlertPopoverProps) {
  const { t } = useTranslation('monitor');
  const { token } = theme.useToken();
  const { data, isLoading } = useDeviceMetricAlerts(deviceId);

  const columns = useMemo<NonNullable<TableProps<DeviceMetricAlertItem>['columns']>>(
    () => [
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
          <Tag color={severityColor(sev, token) ?? 'default'}>{sev ?? '—'}</Tag>
        )
      },
      {
        title: t('alertPopover.column.value'),
        dataIndex: 'last_value',
        width: 80,
        render: (v: string | null) => v ?? '—'
      }
    ],
    [t, token]
  );

  if (alertCount === 0) {
    return <span style={{ color: '#999' }}>{t('alertPopover.normal')}</span>;
  }

  const color = maxSeverity >= 3 ? 'magenta' : 'volcano';

  const content = isLoading ? (
    <Spin size="small" />
  ) : !data?.items?.length ? (
    <Empty description={t('alertPopover.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
  ) : (
    <Table<DeviceMetricAlertItem>
      dataSource={data.items}
      rowKey="id"
      size="small"
      pagination={false}
      style={{ minWidth: 360 }}
      columns={columns}
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
