import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Tag, Button, Space, Statistic, Row, Col, Empty, Tooltip } from 'antd';
import DataTable from '@/components/DataTable';
import {
  ReloadOutlined,
  DashboardOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  getCircuitStatus,
  resetCircuit,
  getAIMetrics,
  getAIHealth,
  type CircuitStatus,
  type AIMetrics
} from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';
import { useConfirm } from '@/utils/confirm';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const META_KEYS = new Set(['metrics_source', 'pid']);

type MetricLabelKey =
  | 'monitor.metric.callsTotal'
  | 'monitor.metric.errorsTotal'
  | 'monitor.metric.promptTokensTotal'
  | 'monitor.metric.completionTokensTotal'
  | 'monitor.metric.tokensTotal'
  | 'monitor.metric.skillRunsTotal'
  | 'monitor.metric.callsToday'
  | 'monitor.metric.errorsToday'
  | 'monitor.metric.promptTokensToday'
  | 'monitor.metric.completionTokensToday'
  | 'monitor.metric.tokensToday'
  | 'monitor.metric.skillRunsToday';

const METRIC_LABEL_KEYS: Record<string, MetricLabelKey> = {
  ai_calls_total: 'monitor.metric.callsTotal',
  ai_errors_total: 'monitor.metric.errorsTotal',
  ai_prompt_tokens_total: 'monitor.metric.promptTokensTotal',
  ai_completion_tokens_total: 'monitor.metric.completionTokensTotal',
  ai_tokens_total: 'monitor.metric.tokensTotal',
  ai_skill_runs_total: 'monitor.metric.skillRunsTotal',
  ai_calls_today: 'monitor.metric.callsToday',
  ai_errors_today: 'monitor.metric.errorsToday',
  ai_prompt_tokens_today: 'monitor.metric.promptTokensToday',
  ai_completion_tokens_today: 'monitor.metric.completionTokensToday',
  ai_tokens_today: 'monitor.metric.tokensToday',
  ai_skill_runs_today: 'monitor.metric.skillRunsToday'
};

const metricLabel = (key: string, t: TFunction<'ai'>) => {
  const k = METRIC_LABEL_KEYS[key];
  return k ? t(k) : key;
};

export default function AIMonitor() {
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const [circuits, setCircuits] = useState<CircuitStatus[]>([]);
  const [metrics, setMetrics] = useState<AIMetrics | null>(null);
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const message = useMessage();

  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const fetchAll = useCallback(async () => {
    if (inFlightRef.current) return; // 前次未返回，跳过避免叠加
    inFlightRef.current = true;
    setLoading(true);
    try {
      const healthPromise = getAIHealth().then(
        (h) => h.configured,
        () => null
      );
      const [c, m] = await Promise.all([getCircuitStatus(), getAIMetrics()]);
      const configured = await healthPromise;
      if (!mountedRef.current) return; // 卸载后不再 setState
      setCircuits(c);
      setMetrics(m);
      setAiConfigured(configured);
    } catch (err) {
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : t('monitor.message.loadFailed'));
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    mountedRef.current = true;
    fetchAll();

    let timer: ReturnType<typeof setInterval> | null = null;

    const startPolling = () => {
      stopPolling();
      timer = setInterval(fetchAll, 10000);
    };
    const stopPolling = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };
    const handleVisibility = () => {
      if (document.hidden) {
        stopPolling();
      } else {
        fetchAll();
        startPolling();
      }
    };

    if (!document.hidden) startPolling();
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      mountedRef.current = false;
      stopPolling();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [fetchAll]);

  const handleReset = (provider: string) => {
    confirm({
      title: t('monitor.reset.title'),
      content: t('monitor.reset.content', { provider }),
      onOk: async () => {
        try {
          await resetCircuit(provider);
          message.success(t('monitor.message.resetDone'));
          fetchAll();
        } catch (err) {
          message.error(err instanceof Error ? err.message : t('monitor.message.resetFailed'));
        }
      }
    });
  };

  const columns: ColumnsType<CircuitStatus> = [
    {
      title: t('monitor.column.provider'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Tag color="blue">{name}</Tag>
    },
    {
      title: tc('field.status'),
      dataIndex: 'open',
      key: 'open',
      width: 100,
      render: (open: boolean) =>
        open ? (
          <Tag color="red">{t('monitor.status.circuitOpen')}</Tag>
        ) : (
          <Tag color="green">{t('monitor.status.normal')}</Tag>
        )
    },
    {
      title: t('monitor.column.failures'),
      dataIndex: 'failures',
      key: 'failures',
      width: 100,
      render: (f: number, record) => (
        <span>
          {f} / {record.threshold}
        </span>
      )
    },
    {
      title: t('monitor.column.cooldownSeconds'),
      dataIndex: 'cooldown_seconds',
      key: 'cooldown_seconds',
      width: 120
    },
    {
      title: t('monitor.column.cooldownRemaining'),
      dataIndex: 'cooldown_remaining',
      key: 'cooldown_remaining',
      width: 100,
      render: (r: number) => (r > 0 ? <Tag color="orange">{r}s</Tag> : <Tag>-</Tag>)
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          danger={record.open}
          onClick={() => handleReset(record.name)}
          disabled={!record.open && record.failures === 0}
        >
          {tc('action.reset')}
        </Button>
      )
    }
  ];

  const metricEntries = metrics ? Object.entries(metrics).filter(([k]) => !META_KEYS.has(k)) : [];

  return (
    <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
      {/* AI 配置就绪态（GET /ai/health）：置于面板顶部，因为"未配置"是解释
          下方指标全为 0 / 熔断表为空的首要原因，先看到它可省一轮排查。 */}
      <Card
        size="small"
        title={
          <Space>
            <ApiOutlined />
            <span>{t('monitor.ready.title')}</span>
          </Space>
        }
      >
        <Space align="center" size="middle" wrap>
          {aiConfigured === null ? (
            <Tag icon={<QuestionCircleOutlined />}>{tc('field.unknown')}</Tag>
          ) : aiConfigured ? (
            <Tag color="green" icon={<CheckCircleOutlined />}>
              {t('monitor.status.configured')}
            </Tag>
          ) : (
            <Tag color="red" icon={<CloseCircleOutlined />}>
              {t('monitor.status.notConfigured')}
            </Tag>
          )}
          <span style={{ fontSize: 13, color: 'rgba(0,0,0,0.45)' }}>
            {aiConfigured === null
              ? t('monitor.ready.hintUnknown')
              : aiConfigured
                ? t('monitor.ready.hintConfigured')
                : t('monitor.ready.hintNotConfigured')}
          </span>
        </Space>
      </Card>

      <Card
        title={
          <Space>
            <DashboardOutlined />
            <span>{t('monitor.metrics.title')}</span>
          </Space>
        }
        extra={
          <Space>
            {/* 数据来源提示：local/error 都不可作为全局依据，
                若不明示会被误读成"全局就是这些数"，且随命中的 worker 漂移。 */}
            {metrics?.metrics_source === 'error' ? (
              <Tooltip title={t('monitor.metrics.source.errorTip')}>
                <Tag color="error">
                  {t('monitor.metrics.source.errorTag', { pid: metrics?.pid })}
                </Tag>
              </Tooltip>
            ) : metrics?.metrics_source === 'local' ? (
              <Tooltip title={t('monitor.metrics.source.localTip')}>
                <Tag color="warning">
                  {t('monitor.metrics.source.localTag', { pid: metrics?.pid })}
                </Tag>
              </Tooltip>
            ) : (
              <Tooltip title={t('monitor.metrics.source.aggregateTip')}>
                <Tag color="success">
                  {t('monitor.metrics.source.aggregateTag', { pid: metrics?.pid })}
                </Tag>
              </Tooltip>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading}>
              {tc('action.refresh')}
            </Button>
          </Space>
        }
      >
        {metricEntries.length === 0 ? (
          <Empty description={t('monitor.metrics.empty')} />
        ) : (
          <Row gutter={[16, 16]}>
            {metricEntries.map(([key, val]) => {
              const isNumeric = typeof val === 'number' && Number.isFinite(val);
              const isRawText = key === 'raw' && typeof val === 'string';
              const isCount = /_(total|today)$/.test(key);
              const label = metricLabel(key, t);
              return (
                <Col key={key} xs={24} sm={12} md={8} lg={isRawText ? 24 : 6}>
                  <Card size="small" type="inner">
                    {isRawText ? (
                      <>
                        <Tooltip title={key}>
                          <div style={{ fontSize: 13, color: 'rgba(0,0,0,0.45)' }}>{key}</div>
                        </Tooltip>
                        <pre
                          style={{ fontSize: 12, maxHeight: 300, overflow: 'auto', marginTop: 4 }}
                        >
                          {val}
                        </pre>
                      </>
                    ) : isNumeric ? (
                      <Statistic
                        title={
                          <Tooltip title={key}>
                            <span style={{ fontSize: 13 }}>{label}</span>
                          </Tooltip>
                        }
                        value={val}
                        precision={isCount ? 0 : val < 100 ? 2 : 0}
                      />
                    ) : (
                      <>
                        <Tooltip title={key}>
                          <div style={{ fontSize: 13, color: 'rgba(0,0,0,0.45)' }}>{key}</div>
                        </Tooltip>
                        <div style={{ fontSize: 20, marginTop: 4 }}>
                          {val === null || val === undefined
                            ? '-'
                            : typeof val === 'object'
                              ? JSON.stringify(val)
                              : String(val)}
                        </div>
                      </>
                    )}
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Card>

      <Card
        title={
          <Space>
            <ThunderboltOutlined />
            <span>{t('monitor.circuit.title')}</span>
          </Space>
        }
      >
        {/* F10 修复：熔断器表 6 列合计约 750px 固定宽，移动端列被压缩。
            加横向滚动后各列保持可读宽度。 */}
        {circuits.length === 0 ? (
          <Empty description={t('monitor.circuit.empty')} />
        ) : (
          <DataTable
            rowKey="name"
            columns={columns}
            dataSource={circuits}
            loading={loading}
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            showCard={false}
            searchable={false}
          />
        )}
      </Card>
    </Space>
  );
}
