import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Table, Tag, Button, Space, Statistic, Row, Col, Empty, Tooltip } from 'antd';
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
import { confirm } from '@/utils/confirm';

const META_KEYS = new Set(['metrics_source', 'pid']);

const METRIC_LABELS: Record<string, string> = {
  ai_calls_total: 'LLM 调用次数（累计）',
  ai_errors_total: '调用失败（累计）',
  ai_prompt_tokens_total: '输入 Token（累计）',
  ai_completion_tokens_total: '输出 Token（累计）',
  ai_tokens_total: 'Token 总消耗（累计）',
  ai_skill_runs_total: '技能执行次数（累计）',
  ai_calls_today: 'LLM 调用次数（今日）',
  ai_errors_today: '调用失败（今日）',
  ai_prompt_tokens_today: '输入 Token（今日）',
  ai_completion_tokens_today: '输出 Token（今日）',
  ai_tokens_today: 'Token 总消耗（今日）',
  ai_skill_runs_today: '技能执行次数（今日）'
};

export default function AIMonitor() {
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
      message.error(err instanceof Error ? err.message : '加载监控数据失败');
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [message]);

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
      title: '重置熔断器',
      content: `确认重置 ${provider} 的熔断器？将清零失败计数。`,
      onOk: async () => {
        try {
          await resetCircuit(provider);
          message.success('已重置');
          fetchAll();
        } catch (err) {
          message.error(err instanceof Error ? err.message : '重置失败');
        }
      }
    });
  };

  const columns: ColumnsType<CircuitStatus> = [
    {
      title: 'Provider',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Tag color="blue">{name}</Tag>
    },
    {
      title: '状态',
      dataIndex: 'open',
      key: 'open',
      width: 100,
      render: (open: boolean) =>
        open ? <Tag color="red">熔断开启</Tag> : <Tag color="green">正常</Tag>
    },
    {
      title: '失败次数',
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
      title: '冷却时间（秒）',
      dataIndex: 'cooldown_seconds',
      key: 'cooldown_seconds',
      width: 120
    },
    {
      title: '剩余冷却',
      dataIndex: 'cooldown_remaining',
      key: 'cooldown_remaining',
      width: 100,
      render: (r: number) => (r > 0 ? <Tag color="orange">{r}s</Tag> : <Tag>-</Tag>)
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          danger={record.open}
          onClick={() => handleReset(record.name)}
          disabled={!record.open && record.failures === 0}
        >
          重置
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
            <span>AI 配置就绪</span>
          </Space>
        }
      >
        <Space align="center" size="middle" wrap>
          {aiConfigured === null ? (
            <Tag icon={<QuestionCircleOutlined />}>未知</Tag>
          ) : aiConfigured ? (
            <Tag color="green" icon={<CheckCircleOutlined />}>
              已配置
            </Tag>
          ) : (
            <Tag color="red" icon={<CloseCircleOutlined />}>
              未配置
            </Tag>
          )}
          <span style={{ fontSize: 13, color: 'rgba(0,0,0,0.45)' }}>
            {aiConfigured === null
              ? '健康探针不可用（接口异常或缺少 ai:use 权限），当前无法判定配置状态'
              : aiConfigured
                ? 'LLM 客户端凭据已就绪，AI 问答 / 诊断 / RAG 能力可用'
                : 'LLM 客户端未配置凭据，AI 问答 / 诊断 / RAG 能力将不可用'}
          </span>
        </Space>
      </Card>

      <Card
        title={
          <Space>
            <DashboardOutlined />
            <span>AI 运行指标</span>
          </Space>
        }
        extra={
          <Space>
            {/* 数据来源提示：local/error 都不可作为全局依据，
                若不明示会被误读成"全局就是这些数"，且随命中的 worker 漂移。 */}
            {metrics?.metrics_source === 'error' ? (
              <Tooltip title="Redis 可达但本次读取失败，以下为本进程兜底数据，不代表全局真实值，请刷新重试">
                <Tag color="error">读取异常 · pid {metrics?.pid}</Tag>
              </Tooltip>
            ) : metrics?.metrics_source === 'local' ? (
              <Tooltip title="Redis 不可用，当前仅为处理本请求的进程内的兜底数据，会随命中的 worker 变化，不可作为全局依据">
                <Tag color="warning">本进程兜底 · pid {metrics?.pid}</Tag>
              </Tooltip>
            ) : (
              <Tooltip title="来自 Redis 聚合，覆盖全部 gunicorn worker 与 celery worker；python_gc 等系统指标仍只反映本进程">
                <Tag color="success">全进程聚合 · pid {metrics?.pid}</Tag>
              </Tooltip>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        {metricEntries.length === 0 ? (
          <Empty description="暂无指标数据" />
        ) : (
          <Row gutter={[16, 16]}>
            {metricEntries.map(([key, val]) => {
              const isNumeric = typeof val === 'number' && Number.isFinite(val);
              const isRawText = key === 'raw' && typeof val === 'string';
              const isCount = /_(total|today)$/.test(key);
              const label = METRIC_LABELS[key] ?? key;
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
            <span>熔断器状态</span>
          </Space>
        }
      >
        {/* F10 修复：熔断器表 6 列合计约 750px 固定宽，移动端列被压缩。
            加横向滚动后各列保持可读宽度。 */}
        {circuits.length === 0 ? (
          <Empty description="暂无熔断器记录（无 AI 调用发生）" />
        ) : (
          <Table
            rowKey="name"
            columns={columns}
            dataSource={circuits}
            loading={loading}
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </Space>
  );
}
