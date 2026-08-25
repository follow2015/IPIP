/**
 * P2-15: 告警统计报表页
 *
 * 多维度告警质量分析：
 * 1. 顶部统计卡片（总数/活跃/已确认/已关闭/失败 + MTTR + 确认率/关闭率）
 * 2. 按级别/类型/状态分布饼图
 * 3. Top N 告警设备 / Top N 告警类型
 * 4. 告警密度时序图（按小时/日桶）
 *
 * 支持时间范围 + 级别 + 桶粒度过滤。
 */
import { useMemo, useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Select,
  DatePicker,
  Space,
  Tag,
  Table,
  Empty,
  theme,
  Segmented
} from 'antd';
import { Pie, Column } from '@ant-design/charts';
import dayjs, { Dayjs } from 'dayjs';
import { useAlertStatistics, type MonitorAlertStatisticsQuery } from '@/services/monitor';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;
const { useToken } = theme;

const SEVERITY_COLOR: Record<string, string> = {
  info: '#52c41a',
  warning: '#faad14',
  critical: '#ff4d4f'
};

const STATUS_COLOR: Record<string, string> = {
  pending: '#d9d9d9',
  sent: '#52c41a',
  failed: '#ff4d4f'
};

export default function MonitorReportsPage() {
  const { token } = useToken();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [severity, setSeverity] = useState<string | undefined>(undefined);
  const [bucket, setBucket] = useState<'hour' | 'day'>('hour');

  const params: MonitorAlertStatisticsQuery = useMemo(() => {
    const p: MonitorAlertStatisticsQuery = { bucket, top_n: 10 };
    if (range && range[0] && range[1]) {
      p.start_date = range[0].toISOString();
      p.end_date = range[1].toISOString();
    }
    if (severity) p.severity = severity;
    return p;
  }, [range, severity, bucket]);

  const { data, isLoading } = useAlertStatistics(params);

  const summary = data?.summary;
  const mttrSeconds = data?.mttr_seconds;
  const mttrDisplay = useMemo(() => {
    if (mttrSeconds == null) return '-';
    if (mttrSeconds < 60) return `${mttrSeconds.toFixed(0)} 秒`;
    if (mttrSeconds < 3600) return `${(mttrSeconds / 60).toFixed(1)} 分钟`;
    return `${(mttrSeconds / 3600).toFixed(2)} 小时`;
  }, [mttrSeconds]);

  
  const severityPieData = useMemo(
    () =>
      (data?.by_severity ?? []).map((x) => ({
        name: x.severity ?? 'unknown',
        value: x.count ?? 0,
        color: SEVERITY_COLOR[x.severity ?? ''] ?? token.colorTextSecondary
      })),
    [data, token]
  );
  const statusPieData = useMemo(
    () =>
      (data?.by_status ?? []).map((x) => ({
        name: x.status ?? 'unknown',
        value: x.count ?? 0,
        color: STATUS_COLOR[x.status ?? ''] ?? token.colorTextSecondary
      })),
    [data, token]
  );
  const typePieData = useMemo(
    () =>
      (data?.by_type ?? []).map((x) => ({ name: x.alert_type ?? 'unknown', value: x.count ?? 0 })),
    [data]
  );

  
  const densityData = useMemo(
    () => (data?.density ?? []).map((x) => ({ time: x.bucket_start ?? '', count: x.count ?? 0 })),
    [data]
  );

  
  const topDeviceColumns = [
    {
      title: '排名',
      key: 'rank',
      render: (_: unknown, __: unknown, idx: number) => idx + 1,
      width: 60
    },
    {
      title: '设备 ID',
      dataIndex: 'device_id',
      key: 'device_id',
      render: (v: number | null) => v ?? '-'
    },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '告警数',
      dataIndex: 'count',
      key: 'count',
      render: (v: number) => <Tag color="red">{v}</Tag>
    }
  ];

  
  const topTypeColumns = [
    {
      title: '排名',
      key: 'rank',
      render: (_: unknown, __: unknown, idx: number) => idx + 1,
      width: 60
    },
    { title: '告警类型', dataIndex: 'alert_type', key: 'alert_type' },
    {
      title: '告警数',
      dataIndex: 'count',
      key: 'count',
      render: (v: number) => <Tag color="blue">{v}</Tag>
    }
  ];

  const pieConfig = (data: { name: string; value: number; color?: string }[], empty: boolean) => ({
    appendPadding: [8, 8, 8, 8] as [number, number, number, number],
    data: empty ? [{ name: '暂无数据', value: 1, color: token.colorBgContainer }] : data,
    angleField: 'value',
    colorField: 'name',
    color: empty ? [token.colorBgContainer] : data.map((d) => d.color ?? token.colorPrimary),
    radius: 0.8,
    innerRadius: 0.6,
    label: { type: 'outer' as const },
    legend: { position: 'bottom' as const, layout: 'horizontal' as const },
    interactions: [{ type: 'element-active' }],
    animation: { appear: { duration: 600, easing: 'easeQuadOut' } }
  });

  const densityConfig = {
    appendPadding: [8, 8, 8, 8] as [number, number, number, number],
    data: densityData,
    xField: 'time',
    yField: 'count',
    height: 280,
    color: token.colorPrimary,
    label: { position: 'top' as const, style: { fill: token.colorTextSecondary, fontSize: 10 } },
    tooltip: { title: 'time', items: [{ field: 'count', name: '告警数' }] },
    axis: {
      x: { labelAutoRotate: true, labelAutoEllipsis: true },
      y: { title: '告警数' }
    },
    animation: { appear: { duration: 600, easing: 'easeQuadOut' } }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="告警统计报表" size="small">
        <Space wrap>
          <RangePicker
            showTime
            value={range}
            onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)}
            placeholder={['开始时间', '结束时间']}
          />
          <Select
            placeholder="告警级别"
            allowClear
            style={{ width: 140 }}
            value={severity}
            onChange={setSeverity}
            options={[
              { label: 'info', value: 'info' },
              { label: 'warning', value: 'warning' },
              { label: 'critical', value: 'critical' }
            ]}
          />
          <Segmented
            options={[
              { label: '按小时', value: 'hour' },
              { label: '按日', value: 'day' }
            ]}
            value={bucket}
            onChange={(v) => setBucket(v as 'hour' | 'day')}
          />
        </Space>
      </Card>

      <Row gutter={16}>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="总告警数"
              value={summary?.total ?? 0}
              valueStyle={{
                color: token.colorText,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="活跃告警"
              value={summary?.active ?? 0}
              valueStyle={{
                color: token.colorWarning,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="已确认"
              value={summary?.acknowledged ?? 0}
              valueStyle={{
                color: token.colorSuccess,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="已关闭"
              value={summary?.closed ?? 0}
              valueStyle={{
                color: token.colorTextSecondary,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="MTTR"
              value={mttrDisplay}
              valueStyle={{
                color: token.colorPrimary,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" loading={isLoading}>
            <Statistic
              title="确认率 / 关闭率"
              value={`${((data?.ack_rate ?? 0) * 100).toFixed(1)}% / ${((data?.close_rate ?? 0) * 100).toFixed(1)}%`}
              valueStyle={{
                color: token.colorText,
                fontFamily: 'Fira Code, monospace',
                fontWeight: 600
              }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card
            title="按级别分布"
            size="small"
            loading={isLoading}
            variant="borderless"
            style={{ height: '100%' }}
          >
            {severityPieData.length === 0 ? (
              <Empty description="暂无数据" style={{ padding: '48px 0' }} />
            ) : (
              <Pie {...pieConfig(severityPieData, false)} height={260} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            title="按状态分布"
            size="small"
            loading={isLoading}
            variant="borderless"
            style={{ height: '100%' }}
          >
            {statusPieData.length === 0 ? (
              <Empty description="暂无数据" style={{ padding: '48px 0' }} />
            ) : (
              <Pie {...pieConfig(statusPieData, false)} height={260} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            title="按类型分布"
            size="small"
            loading={isLoading}
            variant="borderless"
            style={{ height: '100%' }}
          >
            {typePieData.length === 0 ? (
              <Empty description="暂无数据" style={{ padding: '48px 0' }} />
            ) : (
              <Pie {...pieConfig(typePieData, false)} height={260} />
            )}
          </Card>
        </Col>
      </Row>

      <Card
        title={`告警密度时序（${bucket === 'hour' ? '按小时' : '按日'}）`}
        size="small"
        loading={isLoading}
      >
        {densityData.length === 0 ? (
          <Empty description="暂无数据" style={{ padding: '48px 0' }} />
        ) : (
          <Column {...densityConfig} />
        )}
      </Card>

      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card title="Top 10 告警设备" size="small" loading={isLoading}>
            <Table
              columns={topDeviceColumns}
              dataSource={data?.top_devices ?? []}
              rowKey={(_, idx) => String(idx)}
              pagination={false}
              size="small"
              locale={{ emptyText: <Empty description="暂无数据" /> }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="Top 10 告警类型" size="small" loading={isLoading}>
            <Table
              columns={topTypeColumns}
              dataSource={data?.top_types ?? []}
              rowKey={(_, idx) => String(idx)}
              pagination={false}
              size="small"
              locale={{ emptyText: <Empty description="暂无数据" /> }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
