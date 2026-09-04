import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Card,
  Input,
  InputNumber,
  Button,
  Space,
  Spin,
  Alert,
  Typography,
  Empty,
  Tag,
  Tooltip,
  Select
} from 'antd';
import { SendOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import axios from 'axios';
import {
  diagnose,
  parseDiagnosisAnswer,
  verifyRemediation,
  caseToRag,
  getRollbackFailures,
  type DiagnosisResult,
  type VerificationResult,
  type RollbackFailure
} from '@/services/diagnosis';
import {
  listAgenticSkills,
  runAgenticSkill,
  subscribeTaskProgress,
  type AgenticSkillSummary
} from '@/services/ai';
import { usePermission } from '@/hooks/usePermission';
import { useMessage } from '@/hooks/useMessage';
import { confirm } from '@/utils/confirm';
import DiagnosisResultCard from './DiagnosisResultCard';
import CommandConfirmCard from './CommandConfirmCard';

const { Text, Paragraph } = Typography;

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  result?: DiagnosisResult;
  verification?: VerificationResult;
  sessionId?: number;
  viaSkill?: string;
}

export default function DiagnosisChat() {
  const message = useMessage();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [deviceId, setDeviceId] = useState<number | undefined>(undefined);
  const [rollbackFailures, setRollbackFailures] = useState<RollbackFailure[]>([]);
  const [skillName, setSkillName] = useState<string | undefined>(undefined);
  const [skills, setSkills] = useState<AgenticSkillSummary[]>([]);
  const [progressText, setProgressText] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sseCancelRef = useRef<{ cancel: () => void } | null>(null);
  const msgIdRef = useRef(0);
  const mountedRef = useRef(true);

  const { hasPermission } = usePermission();
  const canExecute = hasPermission('ai:execute');
  const canAdmin = hasPermission('ai:admin');

  const nextId = () => ++msgIdRef.current;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      sseCancelRef.current?.cancel();
    };
  }, []);

  useEffect(() => {
    listAgenticSkills()
      .then((list) => {
        if (mountedRef.current) setSkills(list);
      })
      .catch(() => {
      });
  }, []);

  const loadRollbackFailures = useCallback(async () => {
    try {
      const res = await getRollbackFailures();
      if (!mountedRef.current) return;
      setRollbackFailures(res.rollback_failures || []);
    } catch {
    }
  }, []);

  useEffect(() => {
    loadRollbackFailures();
    let timer: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      timer = setInterval(loadRollbackFailures, 60_000);
    };
    const handleVisibility = () => {
      if (document.hidden) {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
      } else {
        loadRollbackFailures();
        if (!timer) startPolling();
      }
    };
    startPolling();
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [loadRollbackFailures]);

  const finishAsync = useCallback((msg?: ChatMessage) => {
    sseCancelRef.current?.cancel();
    sseCancelRef.current = null;
    setProgressText(null);
    setLoading(false);
    if (msg) setMessages((prev) => [...prev, msg]);
  }, []);

  const subscribeProgress = useCallback(
    (taskId: string, skill: string) => {
      sseCancelRef.current?.cancel();
      sseCancelRef.current = subscribeTaskProgress(
        taskId,
        (event) => {
          if (!mountedRef.current) return;
          if (event.type === 'progress') {
            const total = event.total || 0;
            setProgressText(total > 0 ? `第 ${event.progress}/${total} 轮分析中...` : '诊断中...');
            return;
          }
          if (event.type === 'error') {
            finishAsync({
              id: nextId(),
              role: 'assistant',
              content: `诊断失败：${event.message || '任务执行出错，请稍后重试'}`
            });
            return;
          }
          const payload = event.result as { answer?: string; session_id?: number } | null;
          const result = parseDiagnosisAnswer(payload?.answer ?? '');
          finishAsync({
            id: nextId(),
            role: 'assistant',
            content: result.diagnosis,
            result,
            sessionId: event.session_id ?? payload?.session_id,
            viaSkill: skill
          });
        },
        () => {
          if (!mountedRef.current) return;
          finishAsync({
            id: nextId(),
            role: 'assistant',
            content: '进度订阅断开，任务仍在后台执行，请稍后刷新会话查看结果'
          });
        }
      );
    },
    [finishAsync]
  );

  const runSkillAsync = useCallback(
    async (skill: string, question: string) => {
      const idempotencyKey =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      try {
        const resp = await runAgenticSkill(skill, question, idempotencyKey);
        if (!mountedRef.current) return;
        if (resp.finished) {
          finishAsync();
          message.info('该诊断任务已完成（结果已过期），请重新发起');
          return;
        }
        subscribeProgress(resp.task_id, skill);
      } catch (e) {
        if (!mountedRef.current) return;
        finishAsync({
          id: nextId(),
          role: 'assistant',
          content: `诊断失败：${e instanceof Error ? e.message : String(e)}`
        });
      }
    },
    [finishAsync, subscribeProgress, message]
  );

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;

    const userMsg: ChatMessage = { id: nextId(), role: 'user', content: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    if (skillName) {
      await runSkillAsync(skillName, question);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const { result, sessionId } = await diagnose(question, controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        content: result.diagnosis,
        result,
        sessionId
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      if (
        controller.signal.aborted ||
        axios.isCancel(e) ||
        (e as { name?: string })?.name === 'CanceledError'
      )
        return;
      if (!mountedRef.current) return;
      const errMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        content: `诊断失败：${e instanceof Error ? e.message : String(e)}`
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      if (mountedRef.current && !controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  const handleExecuted = useCallback(
    async (msgId: number) => {
      if (!deviceId) return;
      const msg = messages.find((m) => m.id === msgId);
      if (!msg?.result) return;

      const anomalousMetrics = msg.result.anomalous_metrics || [];
      const preSnapshot = msg.result.pre_snapshot || {};
      if (anomalousMetrics.length === 0) {
        message.info('无异常指标记录，跳过自动验证');
        return;
      }

      const VERIFY_TIMEOUT_MS = 30_000;
      const VERIFY_INTERVAL_MS = 3_000;
      const verifyDeadline = Date.now() + VERIFY_TIMEOUT_MS;
      let verification: VerificationResult | null = null;
      message.loading('等待指标刷新后验证...', 0);

      try {
        while (Date.now() < verifyDeadline) {
          verification = await verifyRemediation(deviceId, preSnapshot, anomalousMetrics);
          if (
            verification.status !== 'recovered' ||
            Date.now() > verifyDeadline - VERIFY_INTERVAL_MS
          ) {
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, VERIFY_INTERVAL_MS));
        }
        message.destroy();
        if (!verification) {
          message.error('验证超时，请手动检查');
          return;
        }
        const verifyResult: VerificationResult = verification;
        setMessages((prev) =>
          prev.map((m) => (m.id === msgId ? { ...m, verification: verifyResult } : m))
        );

        if (verifyResult.status === 'recovered') {
          message.success('设备已恢复');
          if (!canAdmin) return;
          const userMsg = [...messages].reverse().find((m) => m.role === 'user' && m.id < msgId);
          const symptom = userMsg?.content || '';
          confirm({
            title: '案例沉淀',
            content: '设备已恢复，是否将本次处置案例沉淀入 RAG 知识库？',
            onOk: async () => {
              try {
                await caseToRag(
                  symptom,
                  msg.result!.evidence,
                  msg.result!.diagnosis,
                  msg.result!.proposed_commands,
                  verifyResult.status
                );
                message.success('案例已入库');
              } catch (err) {
                message.error(`案例入库失败：${err instanceof Error ? err.message : String(err)}`);
              }
            }
          });
        } else if (verifyResult.status === 'partial') {
          message.warning('部分恢复，建议继续诊断');
        } else {
          message.error('未恢复，建议人工介入');
        }
      } catch (e) {
        message.error(`验证失败：${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [deviceId, messages, canAdmin, message]
  );

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      {rollbackFailures.length > 0 && (
        <Alert
          type="error"
          banner
          message={
            <Space>
              <WarningOutlined />
              <Text strong>
                回滚失败告警：{rollbackFailures.length} 个设备处于"已变更未回滚"状态
              </Text>
              <Button size="small" type="link" onClick={loadRollbackFailures}>
                刷新
              </Button>
            </Space>
          }
          description={rollbackFailures.slice(0, 3).map((f) => (
            <Tag key={f.id} color="red">
              设备 {f.device_id} | {f.skill_name} | {f.created_at}
            </Tag>
          ))}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card
        title="智能运维诊断"
        extra={
          <Space>
            <Select
              allowClear
              placeholder="自动路由（自然语言）"
              value={skillName}
              onChange={(v) => setSkillName(v ?? undefined)}
              style={{ width: 200 }}
              disabled={loading}
              options={skills.map((s) => ({
                value: s.name,
                label: s.title || s.name
              }))}
            />
            <InputNumber
              placeholder="设备 ID"
              value={deviceId}
              onChange={(v) => setDeviceId(v ?? undefined)}
              style={{ width: 120 }}
            />
            <Button icon={<ReloadOutlined />} onClick={loadRollbackFailures}>
              检查告警
            </Button>
          </Space>
        }
      >
        <div style={{ minHeight: 400, marginBottom: 16 }}>
          {messages.length === 0 && !loading && (
            <Empty description="输入问题开始诊断，如：'设备 12 CPU 异常'" />
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                marginBottom: 16,
                textAlign: msg.role === 'user' ? 'right' : 'left'
              }}
            >
              <Card
                size="small"
                style={{
                  display: 'inline-block',
                  maxWidth: '80%',
                  textAlign: 'left',
                  background: msg.role === 'user' ? '#e6f4ff' : '#f6ffed'
                }}
              >
                <Paragraph>{msg.content}</Paragraph>
                {msg.result && (
                  <>
                    <DiagnosisResultCard result={msg.result} />
                    {msg.result.proposed_commands?.length > 0 &&
                      deviceId &&
                      (canExecute ? (
                        <CommandConfirmCard
                          commands={msg.result.proposed_commands}
                          deviceId={deviceId}
                          sessionId={msg.sessionId}
                          onExecuted={() => handleExecuted(msg.id)}
                        />
                      ) : (
                        <Tooltip title="无 ai:execute 权限，无法执行修复命令">
                          <span>
                            <CommandConfirmCard
                              commands={msg.result.proposed_commands}
                              deviceId={deviceId}
                              sessionId={msg.sessionId}
                              onExecuted={() => handleExecuted(msg.id)}
                            />
                          </span>
                        </Tooltip>
                      ))}
                  </>
                )}
                {msg.verification && (
                  <Alert
                    type={
                      msg.verification.status === 'recovered'
                        ? 'success'
                        : msg.verification.status === 'partial'
                          ? 'warning'
                          : 'error'
                    }
                    message={`处置验证：${msg.verification.status}`}
                    description={msg.verification.comparison
                      .map(
                        (c) =>
                          `${c.metric}: ${c.pre} → ${c.post} (${
                            c.recovered === null ? '未知' : c.recovered ? '恢复' : '未恢复'
                          })`
                      )
                      .join(' | ')}
                    showIcon
                    style={{ marginTop: 8 }}
                  />
                )}
              </Card>
            </div>
          ))}
          {loading && (
            <Spin tip={progressText ?? '诊断中...'}>
              <div style={{ minHeight: 48 }} />
            </Spin>
          )}
        </div>

        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={handleSend}
            placeholder="描述故障现象，如：'设备 12 CPU 持续 90%'"
            disabled={loading}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}>
            诊断
          </Button>
        </Space.Compact>
      </Card>
    </div>
  );
}
