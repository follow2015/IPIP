/**
 * 监控中心 - 历史趋势页（P2-7）
 *
 * 单设备探测历史可视化：
 * 1. 顶部筛选：设备选择 + 时间范围（1h/24h/7d/30d）+ 协议过滤；
 * 2. 统计卡片：可用率 / 探测次数 / 宕机周期 / 平均·最大·P95 延迟；
 * 3. 延迟趋势折线（按可达状态着色）+ 可达状态时间线（宕机一目了然）；
 * 4. 最近探测明细表。
 *
 * 数据来自 GET /monitor/devices/<id>/history 与 /trends（默认近 7 天窗口）。
 */
import { useMemo, useState } from 'react';
import {
  Card,
  Col,
  Row,
  Select,
  Segmented,
  Space,
  Statistic,
  Tag,
  Typography,
  Empty,
  Spin,
  Button,
  Table
} from 'antd';
import { Line } from '@ant-design/charts';
import {
  LineChartOutlined,
  ArrowDownOutlined,
  RocketOutlined,
  DownloadOutlined
} from '@ant-design/icons';
import { theme } from 'antd';
import { useSearchParams } from 'react-router-dom';
import {
  useMonitorStatuses,
  useProbeHistory,
  useProbeTrends,
  useExportHistory,
  useDeviceMetricKeys,
  useDeviceMetricHistory,
  useDeviceMetricLatest,
  type ProbeHistoryItem,
  type ProbeHistoryQuery,
  type DeviceMetricLatestItem
} from '@/services/monitor';
import { formatDateTime, translateProbeError, ensureUtc } from '@/utils/format';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import DataTable from '@/components/DataTable';
import dayjs from 'dayjs';

const { Text } = Typography;
const { useToken } = theme;

const RANGE_OPTIONS = [
  { label: '1 小时', value: '1h', ms: 60 * 60 * 1000 },
  { label: '24 小时', value: '24h', ms: 24 * 60 * 60 * 1000 },
  { label: '7 天', value: '7d', ms: 7 * 24 * 60 * 60 * 1000 },
  { label: '30 天', value: '30d', ms: 30 * 24 * 60 * 60 * 1000 }
];

const PROTOCOL_OPTIONS = [
  { label: '全部协议', value: '' },
  { label: 'SNMP', value: 'snmp' },
  { label: 'IPMI', value: 'ipmi' },
  { label: 'Zabbix', value: 'zabbix' },
  { label: 'Ping', value: 'ping' }
];

function buildQuery(rangeMs: number, protocol: string): ProbeHistoryQuery {
  const to = new Date();
  const from = new Date(to.getTime() - rangeMs);
  return {
    from: from.toISOString(),
    to: to.toISOString(),
    protocol: protocol || undefined,
    limit: 2000
  };
}

export default function MonitorHistory() {
  const { token } = useToken();
  const [searchParams, setSearchParams] = useSearchParams();
  const [deviceId, setDeviceId] = useState<number>(() => {
    const id = searchParams.get('deviceId');
    return id ? Number(id) : 0;
  });
  const [range, setRange] = useState<string>('24h');
  const [protocol, setProtocol] = useState<string>('');
  const table = useTable({ initialPerPage: 20 });

  const { data: statusData, isLoading: devicesLoading } = useMonitorStatuses({ per_page: 200 });
  const deviceOptions = useMemo(
    () =>
      (statusData?.items ?? []).map((d) => ({
        label: d.device_name ? `${d.device_name} (#${d.device_id})` : `#${d.device_id}`,
        value: d.device_id
      })),
    [statusData]
  );

  const rangeMs = RANGE_OPTIONS.find((r) => r.value === range)?.ms ?? RANGE_OPTIONS[1].ms;
  const query = useMemo(() => buildQuery(rangeMs, protocol), [rangeMs, protocol]);

  const handleDeviceChange = (id: number) => {
    setDeviceId(id);
    setSearchParams(
      (prev) => {
        if (id > 0) prev.set('deviceId', String(id));
        else prev.delete('deviceId');
        return prev;
      },
      { replace: true }
    );
  };

  const { data: history, isLoading: historyLoading } = useProbeHistory(deviceId, query);
  const { data: trends, isLoading: trendsLoading } = useProbeTrends(deviceId, query);

  const [selectedMetricKey, setSelectedMetricKey] = useState<string | undefined>(undefined);
  const { data: metricKeysData } = useDeviceMetricKeys(deviceId);
  const { data: metricLatestData } = useDeviceMetricLatest(deviceId);
  const metricKeyOptions = (metricKeysData?.items ?? []).map((k) => ({ label: k, value: k }));
  const metricHistoryQuery = useMemo(
    () => ({ from: query.from, to: query.to, limit: 2000 }),
    [query.from, query.to]
  );
  const { data: metricHistory, isLoading: metricHistoryLoading } = useDeviceMetricHistory(
    deviceId,
    selectedMetricKey,
    metricHistoryQuery
  );
  const metricSeries = useMemo(() => {
    const items = metricHistory?.items ?? [];
    return items
      .map((i) => {
        const num = i.value != null ? Number(i.value) : NaN;
        return {
          time: i.collected_at
            ? dayjs(ensureUtc(i.collected_at)).format('YYYY-MM-DD HH:mm:ss')
            : '',
          value: isFinite(num) ? num : null,
          index: i.index_key || 'default',
          breached: i.breached
        };
      })
      .filter((r) => r.value != null);
  }, [metricHistory]);

  const message = useMessage();
  const exportHistory = useExportHistory();

  const latencyData = useMemo(
    () =>
      (history?.items ?? [])
        .filter((i: ProbeHistoryItem) => i.reachable && i.latency_ms != null)
        .map((i) => ({
          time: i.probed_at ? dayjs(ensureUtc(i.probed_at)).format('YYYY-MM-DD HH:mm:ss') : '',
          latency: i.latency_ms as number
        })),
    [history]
  );

  const reachData = useMemo(
    () =>
      (history?.items ?? []).map((i) => ({
        time: i.probed_at ? dayjs(ensureUtc(i.probed_at)).format('YYYY-MM-DD HH:mm:ss') : '',
        reachable: i.reachable ? 1 : 0,
        state: i.reachable ? '可达' : '不可达'
      })),
    [history]
  );

  const hasData = (history?.items?.length ?? 0) > 0;

  const latencyConfig = useMemo(
    () => ({
      data: latencyData,
      xField: 'time' as const,
      yField: 'latency' as const,
      height: 280,
      point: { size: 3 },
      style: { stroke: token.colorSuccess },
      axis: {
        y: { title: '延迟 (ms)' },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [latencyData, token.colorSuccess]
  );

  const reachConfig = useMemo(
    () => ({
      data: reachData,
      xField: 'time' as const,
      yField: 'reachable' as const,
      colorField: 'state' as const,
      height: 220,
      shapeField: 'hv' as const,
      scale: {
        color: {
          domain: ['可达', '不可达'],
          range: [token.colorSuccess, token.colorError]
        }
      },
      axis: {
        y: {
          title: '可达状态',
          tickCount: 2,
          labelFormatter: (v: number) => (v === 1 ? '可达' : '不可达')
        },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [reachData, token.colorSuccess, token.colorError]
  );

  const columns = [
    {
      title: '探测时间',
      dataIndex: 'probed_at',
      key: 'probed_at',
      width: 200,
      render: (v: string | null) => formatDateTime(v)
    },
    {
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 100,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '可达',
      dataIndex: 'reachable',
      key: 'reachable',
      width: 90,
      render: (v: boolean) =>
        v ? <Tag color="success">可达</Tag> : <Tag color="error">不可达</Tag>
    },
    {
      title: '延迟(ms)',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 100,
      render: (v: number | null) => (v == null ? '—' : v)
    },
    {
      title: '连续失败',
      dataIndex: 'consecutive_failures',
      key: 'consecutive_failures',
      width: 100
    },
    {
      title: '告警',
      dataIndex: 'is_alert',
      key: 'is_alert',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="warning">是</Tag> : '—')
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      ellipsis: true,
      render: (v: string | null) => translateProbeError(v)
    }
  ];

  return (
    <div style={{ padding: 16 }}>
      <Card size="small" variant="borderless" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Space>
            <Text strong>设备</Text>
            <Select
              showSearch
              style={{ width: 280 }}
              placeholder="选择监控设备"
              loading={devicesLoading}
              value={deviceId || undefined}
              options={deviceOptions}
              onChange={(v) => handleDeviceChange(v)}
              optionFilterProp="label"
              notFoundContent="暂无可监控设备"
            />
          </Space>
          <Space>
            <Text strong>时间范围</Text>
            <Segmented
              options={RANGE_OPTIONS.map((r) => ({ label: r.label, value: r.value }))}
              value={range}
              onChange={(v) => setRange(v as string)}
            />
          </Space>
          <Space>
            <Text strong>协议</Text>
            <Select
              style={{ width: 140 }}
              value={protocol}
              options={PROTOCOL_OPTIONS}
              onChange={(v) => setProtocol(v)}
            />
          </Space>
          {/* G5: 导出探测历史 CSV */}
          {deviceId > 0 && (
            <Button
              icon={<DownloadOutlined />}
              loading={exportHistory.isPending}
              onClick={async () => {
                try {
                  await exportHistory.mutateAsync({
                    deviceId,
                    start_date: query.from,
                    end_date: query.to
                  });
                } catch (err: unknown) {
                  message.error(err instanceof Error ? err.message : '导出失败');
                }
              }}
            >
              导出 CSV
            </Button>
          )}
        </Space>
      </Card>

      {deviceId <= 0 ? (
        <Card variant="borderless">
          <Empty description="请先选择一台监控设备查看历史趋势" />
        </Card>
      ) : (
        <Spin spinning={historyLoading || trendsLoading}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="可用率"
                  value={trends?.uptime_pct ?? 0}
                  precision={1}
                  suffix="%"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                  styles={{
                    content: {
                      color:
                        (trends?.uptime_pct ?? 100) >= 99 ? token.colorSuccess : token.colorWarning
                    }
                  }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="探测次数"
                  value={trends?.total ?? 0}
                  prefix={<RocketOutlined />}
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="宕机周期"
                  value={trends?.down_episodes ?? 0}
                  prefix={<ArrowDownOutlined />}
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                  styles={{
                    content: {
                      color: (trends?.down_episodes ?? 0) > 0 ? token.colorError : undefined
                    }
                  }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="平均延迟"
                  value={trends?.avg_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="最大延迟"
                  value={trends?.max_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title="P95 延迟"
                  value={trends?.p95_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={24}>
              <Card
                title="延迟趋势与可达状态（双轴）"
                size="small"
                variant="borderless"
                extra={<LineChartOutlined style={{ color: token.colorTextSecondary }} />}
              >
                {hasData && latencyData.length > 0 ? (
                  <>
                    <Line {...latencyConfig} />
                    <div style={{ marginTop: 8 }}>
                      <Line {...reachConfig} />
                    </div>
                  </>
                ) : (
                  <Empty description="暂无延迟数据" style={{ padding: '48px 0' }} />
                )}
              </Card>
            </Col>
          </Row>

          {/* P1-9: 指标当前值 */}
          {deviceId > 0 && (metricLatestData?.items ?? []).length > 0 && (
            <Card title="指标当前值" size="small" variant="borderless" style={{ marginTop: 16 }}>
              <Table<DeviceMetricLatestItem>
                size="small"
                rowKey={(r) => `${r.metric_key}:${r.index_key}`}
                dataSource={metricLatestData?.items ?? []}
                pagination={false}
                columns={[
                  { title: '指标键', dataIndex: 'metric_key', width: 160 },
                  { title: '实例', dataIndex: 'index_key', width: 120 },
                  {
                    title: '当前值',
                    dataIndex: 'value',
                    render: (v: string | null) => v ?? '-'
                  },
                  {
                    title: '级别',
                    dataIndex: 'severity',
                    width: 80,
                    render: (s: string | null) =>
                      s ? (
                        <Tag color={s === 'crit' ? 'red' : s === 'warn' ? 'orange' : 'green'}>
                          {s}
                        </Tag>
                      ) : (
                        '-'
                      )
                  },
                  {
                    title: '状态',
                    dataIndex: 'breached',
                    width: 80,
                    render: (b: boolean) =>
                      b ? <Tag color="error">越限</Tag> : <Tag color="success">正常</Tag>
                  },
                  {
                    title: '采集时间',
                    dataIndex: 'collected_at',
                    width: 180,
                    render: (t: string) => (t ? dayjs(t).format('MM-DD HH:mm:ss') : '-')
                  }
                ]}
              />
            </Card>
          )}

          {/* P0-3d 指标值趋势图 */}
          {deviceId > 0 && metricKeyOptions.length > 0 && (
            <Card
              title="指标趋势"
              size="small"
              variant="borderless"
              style={{ marginTop: 16 }}
              extra={
                <Select
                  showSearch
                  style={{ width: 220 }}
                  placeholder="选择指标"
                  value={selectedMetricKey}
                  options={metricKeyOptions}
                  onChange={(v) => setSelectedMetricKey(v)}
                  optionFilterProp="label"
                  allowClear
                />
              }
            >
              {selectedMetricKey ? (
                metricHistoryLoading ? (
                  <Empty description="加载中..." style={{ padding: '48px 0' }} />
                ) : metricSeries.length > 0 ? (
                  <Line
                    data={metricSeries}
                    xField="time"
                    yField="value"
                    colorField="index"
                    shape="smooth"
                    height={320}
                    axis={{
                      y: { title: '值' },
                      x: { labelAutoRotate: true }
                    }}
                    scale={{ y: { nice: true } }}
                    tooltip={{
                      title: 'time',
                      items: [
                        { field: 'index', name: '索引' },
                        { field: 'value', name: '值' }
                      ]
                    }}
                    legend={{ color: { position: 'top' } }}
                  />
                ) : (
                  <Empty description="该指标在所选时间范围内无数据" style={{ padding: '48px 0' }} />
                )
              ) : (
                <Empty description="请选择一个指标查看趋势" style={{ padding: '48px 0' }} />
              )}
            </Card>
          )}

          <Card title="最近探测明细" size="small" variant="borderless" style={{ marginTop: 16 }}>
            <DataTable<ProbeHistoryItem>
              columns={columns}
              dataSource={history?.items ?? []}
              rowKey={(r) => String(r.id)}
              total={history?.items?.length ?? 0}
              searchable={false}
              showCard={false}
              tableProps={table}
            />
          </Card>
        </Spin>
      )}
    </div>
  );
}
