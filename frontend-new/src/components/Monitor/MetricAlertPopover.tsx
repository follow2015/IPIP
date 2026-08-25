import { Popover, Table, Tag, Spin, Empty } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import { useDeviceMetricAlerts } from '@/services/monitor';

const METRIC_KEY_LABEL: Record<string, string> = {
  temperature: '温度',
  port_updown: '端口状态',
  disk_failure: '硬盘故障',
  raid_failure: 'RAID故障',
  monitor_interrupted: '监控中断'
};

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
  const { data, isLoading } = useDeviceMetricAlerts(deviceId);

  if (alertCount === 0) {
    return <span style={{ color: '#999' }}>正常</span>;
  }

  const color = maxSeverity >= 3 ? 'magenta' : 'volcano';

  const content = isLoading ? (
    <Spin size="small" />
  ) : !data?.items?.length ? (
    <Empty description="暂无活跃告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  ) : (
    <Table
      dataSource={data.items}
      rowKey="id"
      size="small"
      pagination={false}
      style={{ minWidth: 360 }}
      columns={[
        {
          title: '指标',
          dataIndex: 'metric_key',
          width: 90,
          render: (key: string) => METRIC_KEY_LABEL[key] ?? key
        },
        {
          title: '实例',
          dataIndex: 'index_key',
          width: 120,
          render: (v: string) => v || '—',
          ellipsis: true
        },
        {
          title: '级别',
          dataIndex: 'severity',
          width: 70,
          render: (sev: string | null) => (
            <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>{sev ?? '—'}</Tag>
          )
        },
        {
          title: '当前值',
          dataIndex: 'last_value',
          width: 80,
          render: (v: string | null) => v ?? '—'
        }
      ]}
    />
  );

  return (
    <Popover title="指标告警明细" content={content} trigger="click" placement="left">
      <Tag color={color} icon={<WarningOutlined />} style={{ cursor: 'pointer' }}>
        {alertCount} 条告警
      </Tag>
    </Popover>
  );
}

export default MetricAlertPopover;
