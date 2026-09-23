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
  Button
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
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';
import { useResetPageOnDeps } from '@/hooks/useResetPageOnDeps';
import { useTable } from '@/hooks/useTable';
import DataTable from '@/components/DataTable';
import dayjs from 'dayjs';
import type { TFunction } from 'i18next';

const { Text } = Typography;
const { useToken } = theme;

const getRangeOptions = (t: TFunction<'monitor'>) => [
  { label: t('history.range.h1'), value: '1h', ms: 60 * 60 * 1000 },
  { label: t('history.range.h24'), value: '24h', ms: 24 * 60 * 60 * 1000 },
  { label: t('history.range.d7'), value: '7d', ms: 7 * 24 * 60 * 60 * 1000 },
  { label: t('history.range.d30'), value: '30d', ms: 30 * 24 * 60 * 60 * 1000 }
];

const getProtocolOptions = (t: TFunction<'monitor'>) => [
  { label: t('history.protocolAll'), value: '' },
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
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
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

  const rangeOptions = getRangeOptions(t);
  const rangeMs = rangeOptions.find((r) => r.value === range)?.ms ?? rangeOptions[1].ms;
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
  const historyItems = history?.items ?? [];

  const { setPage: setHistoryPage } = table;
  useResetPageOnDeps(setHistoryPage, [deviceId, range, protocol]);
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
        state: i.reachable ? t('status.reachable') : t('status.unreachable')
      })),
    [history, t]
  );

  const hasData = (history?.items?.length ?? 0) > 0;

  const qualityTrends = (trends?.quality_samples ?? 0) > 0 ? trends : null;

  const formatPct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`);

  const qualityItems = useMemo(
    () =>
      (history?.items ?? []).filter(
        (i: ProbeHistoryItem) => i.loss_pct != null || i.jitter_ms != null
      ),
    [history]
  );
  const hasQuality = qualityItems.length > 0;

  const lossData = useMemo(
    () =>
      (history?.items ?? [])
        .filter((i: ProbeHistoryItem) => i.loss_pct != null)
        .map((i) => ({
          time: i.probed_at ? dayjs(ensureUtc(i.probed_at)).format('YYYY-MM-DD HH:mm:ss') : '',
          loss: i.loss_pct as number
        })),
    [history]
  );

  const jitterData = useMemo(
    () =>
      (history?.items ?? [])
        .filter((i: ProbeHistoryItem) => i.jitter_ms != null)
        .map((i) => ({
          time: i.probed_at ? dayjs(ensureUtc(i.probed_at)).format('YYYY-MM-DD HH:mm:ss') : '',
          jitter: i.jitter_ms as number
        })),
    [history]
  );

  const lossConfig = useMemo(
    () => ({
      data: lossData,
      xField: 'time' as const,
      yField: 'loss' as const,
      height: 220,
      point: { size: 3 },
      style: { stroke: token.colorError },
      axis: {
        y: { title: '丢包率 (%)' },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [lossData, token.colorError]
  );

  const jitterConfig = useMemo(
    () => ({
      data: jitterData,
      xField: 'time' as const,
      yField: 'jitter' as const,
      height: 220,
      point: { size: 3 },
      style: { stroke: token.colorWarning },
      axis: {
        y: { title: '抖动 (ms)' },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [jitterData, token.colorWarning]
  );

  const renderLoss = (v: number | null) =>
    v == null ? (
      <Text type="secondary">—</Text>
    ) : v > 0 ? (
      <Tag color="error">{v}%</Tag>
    ) : (
      <Tag color="success">0%</Tag>
    );

  const renderJitter = (v: number | null) =>
    v == null ? (
      <Text type="secondary">—</Text>
    ) : (
      <Tag color={v > 20 ? 'error' : v > 5 ? 'warning' : 'success'}>{v} ms</Tag>
    );

  const latencyConfig = useMemo(
    () => ({
      data: latencyData,
      xField: 'time' as const,
      yField: 'latency' as const,
      height: 280,
      point: { size: 3 },
      style: { stroke: token.colorSuccess },
      axis: {
        y: { title: t('history.chart.latencyAxis') },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [latencyData, token.colorSuccess, t]
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
          domain: [t('status.reachable'), t('status.unreachable')],
          range: [token.colorSuccess, token.colorError]
        }
      },
      axis: {
        y: {
          title: t('history.chart.reachAxis'),
          tickCount: 2,
          labelFormatter: (v: number) =>
            v === 1 ? t('status.reachable') : t('status.unreachable')
        },
        x: { title: false }
      },
      tooltip: { title: 'time' },
      legend: false,
      animation: false
    }),
    [reachData, token.colorSuccess, token.colorError, t]
  );

  const columns = [
    {
      title: t('column.probedAt'),
      dataIndex: 'probed_at',
      key: 'probed_at',
      width: 200,
      render: (v: string | null) => formatDateTime(v)
    },
    {
      title: t('column.protocol'),
      dataIndex: 'protocol',
      key: 'protocol',
      width: 100,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: t('status.reachable'),
      dataIndex: 'reachable',
      key: 'reachable',
      width: 90,
      render: (v: boolean) =>
        v ? (
          <Tag color="success">{t('status.reachable')}</Tag>
        ) : (
          <Tag color="error">{t('status.unreachable')}</Tag>
        )
    },
    {
      title: t('column.latency'),
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 100,
      render: (v: number | null) => (v == null ? '—' : v)
    },
    {
      title: '丢包率',
      dataIndex: 'loss_pct',
      key: 'loss_pct',
      width: 110,
      render: (v: number | null) => renderLoss(v)
    },
    {
      title: '抖动(ms)',
      dataIndex: 'jitter_ms',
      key: 'jitter_ms',
      width: 110,
      render: (v: number | null) => renderJitter(v)
    },
    {
      title: '采样包数',
      dataIndex: 'samples',
      key: 'samples',
      width: 100,
      render: (v: number | null) => (v == null ? '—' : v)
    },
    {
      title: t('column.consecutiveFailures'),
      dataIndex: 'consecutive_failures',
      key: 'consecutive_failures',
      width: 100
    },
    {
      title: t('column.alert'),
      dataIndex: 'is_alert',
      key: 'is_alert',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="warning">{t('column.yes')}</Tag> : '—')
    },
    {
      title: t('column.error'),
      dataIndex: 'error',
      key: 'error',
      ellipsis: true,
      render: (v: string | null) => translateProbeError(v, td)
    }
  ];

  const renderProbeCard = (r: ProbeHistoryItem) => (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Text style={{ fontSize: 12 }}>{formatDateTime(r.probed_at)}</Text>
        <Space size={4} wrap>
          <Tag color="blue">{r.protocol}</Tag>
          {r.reachable ? (
            <Tag color="success">{t('status.reachable')}</Tag>
          ) : (
            <Tag color="error">{t('status.unreachable')}</Tag>
          )}
          {r.is_alert && <Tag color="warning">{t('column.alert')}</Tag>}
        </Space>
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {t('history.cardSummary', {
          latency: r.latency_ms == null ? '—' : `${r.latency_ms} ms`,
          failures: r.consecutive_failures
        })}
        {r.loss_pct != null && ` · 丢包 ${r.loss_pct}%`}
        {r.jitter_ms != null && ` · 抖动 ${r.jitter_ms} ms`}
      </Text>
      {r.error && (
        <Text type="danger" style={{ fontSize: 12 }}>
          {translateProbeError(r.error, td)}
        </Text>
      )}
    </Space>
  );

  return (
    <div style={{ padding: 16 }}>
      <Card size="small" variant="borderless" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Space>
            <Text strong>{t('column.device')}</Text>
            <Select
              showSearch
              style={{ width: 280 }}
              placeholder={t('history.selectDevice')}
              loading={devicesLoading}
              value={deviceId || undefined}
              options={deviceOptions}
              onChange={(v) => handleDeviceChange(v)}
              optionFilterProp="label"
              notFoundContent={t('history.noDevice')}
            />
          </Space>
          <Space>
            <Text strong>{t('history.timeRange')}</Text>
            <Segmented
              options={rangeOptions.map((r) => ({ label: r.label, value: r.value }))}
              value={range}
              onChange={(v) => setRange(v as string)}
            />
          </Space>
          <Space>
            <Text strong>{t('column.protocol')}</Text>
            <Select
              style={{ width: 140 }}
              value={protocol}
              options={getProtocolOptions(t)}
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
                  message.error(err instanceof Error ? err.message : t('export.failed'));
                }
              }}
            >
              {t('export.csv')}
            </Button>
          )}
        </Space>
      </Card>

      {deviceId <= 0 ? (
        <Card variant="borderless">
          <Empty description={t('history.pleaseSelectDevice')} />
        </Card>
      ) : (
        <Spin spinning={historyLoading || trendsLoading}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title={t('history.stat.uptime')}
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
                  title={t('history.stat.probes')}
                  value={trends?.total ?? 0}
                  prefix={<RocketOutlined />}
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title={t('history.stat.downEpisodes')}
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
                  title={t('history.stat.avgLatency')}
                  value={trends?.avg_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title={t('history.stat.maxLatency')}
                  value={trends?.max_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" variant="borderless">
                <Statistic
                  title={t('history.stat.p95Latency')}
                  value={trends?.p95_latency_ms ?? 0}
                  suffix="ms"
                  valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                />
              </Card>
            </Col>
          </Row>

          {/* P0-2 ping 质量卡片：仅在该设备窗口内确有质量样本时出现。
              没有样本时整块不渲染 —— 不拿 0% 填四个卡片说"一切正常"。 */}
          {qualityTrends && (
            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={12} sm={8} md={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title="平均丢包率"
                    value={formatPct(qualityTrends.avg_loss_pct)}
                    valueStyle={{
                      fontFamily: 'Fira Code, monospace',
                      fontWeight: 600,
                      color:
                        (qualityTrends.avg_loss_pct ?? 0) > 0
                          ? token.colorError
                          : token.colorSuccess
                    }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title="最大丢包率"
                    value={formatPct(qualityTrends.max_loss_pct)}
                    valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title="平均抖动"
                    value={
                      qualityTrends.avg_jitter_ms == null
                        ? '—'
                        : `${qualityTrends.avg_jitter_ms} ms`
                    }
                    valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title="质量采样次数"
                    value={qualityTrends.quality_samples}
                    valueStyle={{ fontFamily: 'Fira Code, monospace', fontWeight: 600 }}
                  />
                </Card>
              </Col>
            </Row>
          )}

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={24}>
              <Card
                title={t('history.chart.trendTitle')}
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
                  <Empty
                    description={t('history.chart.noLatencyData')}
                    style={{ padding: '48px 0' }}
                  />
                )}
              </Card>
            </Col>
          </Row>

          {/* P0-2 ping 质量趋势：丢包率与抖动分开画。
              刻意**不合并成一张双 Y 轴图**：% 与 ms 量纲不同，共用一张图时
              两条线的相对高低会被 Y 轴缩放随机决定，读图人会得出错误结论。
              也没有与延迟合并：延迟高但零丢包（链路正常、只是远）与
              延迟不高却偶发丢包（链路有损）是两种完全不同的故障。 */}
          {hasQuality && (
            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} lg={24}>
                <Card
                  title="Ping 质量趋势（丢包率 / 抖动）"
                  size="small"
                  variant="borderless"
                  extra={<LineChartOutlined style={{ color: token.colorTextSecondary }} />}
                >
                  {lossData.length > 0 ? (
                    <Line {...lossConfig} />
                  ) : (
                    <Empty description="暂无丢包率数据" style={{ padding: '24px 0' }} />
                  )}
                  <div style={{ marginTop: 8 }}>
                    {jitterData.length > 0 ? (
                      <Line {...jitterConfig} />
                    ) : (
                      <Empty description="暂无抖动数据" style={{ padding: '24px 0' }} />
                    )}
                  </div>
                </Card>
              </Col>
            </Row>
          )}

          {/* P1-9: 指标当前值 */}
          {deviceId > 0 && (metricLatestData?.items ?? []).length > 0 && (
            <Card
              title={t('history.latest.title')}
              size="small"
              variant="borderless"
              style={{ marginTop: 16 }}
            >
              <DataTable<DeviceMetricLatestItem>
                size="small"
                searchable={false}
                showCard={false}
                rowKey={(r) => `${r.metric_key}:${r.index_key}`}
                dataSource={metricLatestData?.items ?? []}
                pagination={false}
                columns={[
                  { title: t('column.metricKey'), dataIndex: 'metric_key', width: 160 },
                  { title: t('column.instance'), dataIndex: 'index_key', width: 120 },
                  {
                    title: t('column.currentValue'),
                    dataIndex: 'value',
                    render: (v: string | null) => v ?? '-'
                  },
                  {
                    title: tc('field.level'),
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
                    title: tc('field.status'),
                    dataIndex: 'breached',
                    width: 80,
                    render: (b: boolean) =>
                      b ? (
                        <Tag color="error">{t('history.latest.breached')}</Tag>
                      ) : (
                        <Tag color="success">{t('alertPopover.normal')}</Tag>
                      )
                  },
                  {
                    title: t('column.collectedAt'),
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
              title={t('history.trend.title')}
              size="small"
              variant="borderless"
              style={{ marginTop: 16 }}
              extra={
                <Select
                  showSearch
                  style={{ width: 220 }}
                  placeholder={t('history.trend.selectMetric')}
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
                  <Empty description={tc('message.loading')} style={{ padding: '48px 0' }} />
                ) : metricSeries.length > 0 ? (
                  <Line
                    data={metricSeries}
                    xField="time"
                    yField="value"
                    colorField="index"
                    shape="smooth"
                    height={320}
                    axis={{
                      y: { title: t('history.trend.valueAxis') },
                      x: { labelAutoRotate: true }
                    }}
                    scale={{ y: { nice: true } }}
                    tooltip={{
                      title: 'time',
                      items: [
                        { field: 'index', name: t('history.trend.indexName') },
                        { field: 'value', name: t('history.trend.valueName') }
                      ]
                    }}
                    legend={{ color: { position: 'top' } }}
                  />
                ) : (
                  <Empty description={t('history.trend.noData')} style={{ padding: '48px 0' }} />
                )
              ) : (
                <Empty
                  description={t('history.trend.pleaseSelect')}
                  style={{ padding: '48px 0' }}
                />
              )}
            </Card>
          )}

          <Card
            title={t('history.recentProbes')}
            size="small"
            variant="borderless"
            style={{ marginTop: 16 }}
          >
            <DataTable<ProbeHistoryItem>
              columns={columns}
              dataSource={historyItems}
              rowKey={(r) => String(r.id)}
              total={historyItems.length}
              searchable={false}
              showCard={false}
              tableProps={table}
              mobileCardMode
              cardRender={renderProbeCard}
            />
          </Card>
        </Spin>
      )}
    </div>
  );
}
