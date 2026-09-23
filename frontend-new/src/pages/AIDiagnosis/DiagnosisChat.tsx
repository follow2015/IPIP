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
import { useConfirm } from '@/utils/confirm';
import { useTranslation } from 'react-i18next';
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
  const confirm = useConfirm();
  const message = useMessage();
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
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
            setProgressText(
              total > 0
                ? t('diagnosis.progress.round', { current: event.progress, total })
                : t('diagnosis.progress.analyzing')
            );
            return;
          }
          if (event.type === 'error') {
            finishAsync({
              id: nextId(),
              role: 'assistant',
              content: t('diagnosis.message.failed', {
                reason: event.message || t('diagnosis.message.taskError')
              })
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
            content: t('diagnosis.message.progressDisconnected')
          });
        }
      );
    },
    [finishAsync, t]
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
          message.info(t('diagnosis.message.taskFinishedExpired'));
          return;
        }
        subscribeProgress(resp.task_id, skill);
      } catch (e) {
        if (!mountedRef.current) return;
        finishAsync({
          id: nextId(),
          role: 'assistant',
          content: t('diagnosis.message.failed', {
            reason: e instanceof Error ? e.message : String(e)
          })
        });
      }
    },
    [finishAsync, subscribeProgress, message, t]
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
        content: t('diagnosis.message.failed', {
          reason: e instanceof Error ? e.message : String(e)
        })
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
        message.info(t('diagnosis.message.noAnomalousSkip'));
        return;
      }

      const VERIFY_TIMEOUT_MS = 30_000;
      const VERIFY_INTERVAL_MS = 3_000;
      const verifyDeadline = Date.now() + VERIFY_TIMEOUT_MS;
      let verification: VerificationResult | null = null;
      message.loading(t('diagnosis.message.waitingVerify'), 0);

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
          message.error(t('diagnosis.message.verifyTimeout'));
          return;
        }
        const verifyResult: VerificationResult = verification;
        setMessages((prev) =>
          prev.map((m) => (m.id === msgId ? { ...m, verification: verifyResult } : m))
        );

        if (verifyResult.status === 'recovered') {
          message.success(t('diagnosis.message.recovered'));
          if (!canAdmin) return;
          const userMsg = [...messages].reverse().find((m) => m.role === 'user' && m.id < msgId);
          const symptom = userMsg?.content || '';
          confirm({
            title: t('diagnosis.persist.title'),
            content: t('diagnosis.persist.content'),
            onOk: async () => {
              try {
                await caseToRag(
                  symptom,
                  msg.result!.evidence,
                  msg.result!.diagnosis,
                  msg.result!.proposed_commands,
                  verifyResult.status
                );
                message.success(t('diagnosis.message.caseSaved'));
              } catch (err) {
                message.error(
                  t('diagnosis.message.caseSaveFailed', {
                    reason: err instanceof Error ? err.message : String(err)
                  })
                );
              }
            }
          });
        } else if (verifyResult.status === 'partial') {
          message.warning(t('diagnosis.message.partial'));
        } else {
          message.error(t('diagnosis.message.notRecovered'));
        }
      } catch (e) {
        message.error(
          t('diagnosis.message.verifyFailed', {
            reason: e instanceof Error ? e.message : String(e)
          })
        );
      }
    },
    [confirm, deviceId, messages, canAdmin, message, t]
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
                {t('diagnosis.rollback.alert', { count: rollbackFailures.length })}
              </Text>
              <Button size="small" type="link" onClick={loadRollbackFailures}>
                {tc('action.refresh')}
              </Button>
            </Space>
          }
          description={rollbackFailures.slice(0, 3).map((f) => (
            <Tag key={f.id} color="red">
              {/* 设备名快照优先、回落裸 ID：这条告警说的正是"某台设备卡在
                  已变更未回滚"，而设备很可能已被删除 ⇒ 只认 ID 会显示成
                  `设备 null`（后端已把 device_id 置空、靠快照列自证）。 */}
              {t('diagnosis.rollback.tag', {
                deviceId: f.device_name ?? f.device_id,
                skill: f.skill_name,
                time: f.created_at
              })}
            </Tag>
          ))}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card
        title={t('diagnosis.title')}
        extra={
          <Space>
            <Select
              allowClear
              placeholder={t('diagnosis.field.autoRoute')}
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
              placeholder={t('diagnosis.field.deviceId')}
              value={deviceId}
              onChange={(v) => setDeviceId(v ?? undefined)}
              style={{ width: 120 }}
            />
            <Button icon={<ReloadOutlined />} onClick={loadRollbackFailures}>
              {t('diagnosis.action.checkAlerts')}
            </Button>
          </Space>
        }
      >
        <div style={{ minHeight: 400, marginBottom: 16 }}>
          {messages.length === 0 && !loading && (
            <Empty description={t('diagnosis.empty')} />
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
                        <Tooltip title={t('diagnosis.tooltip.noExecutePermission')}>
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
                    message={t('diagnosis.verify.title', { status: msg.verification.status })}
                    description={msg.verification.comparison
                      .map((c) =>
                        t('diagnosis.verify.item', {
                          metric: c.metric,
                          pre: c.pre,
                          post: c.post,
                          statusText:
                            c.recovered === null
                              ? tc('field.unknown')
                              : c.recovered
                                ? t('diagnosis.verify.recovered')
                                : t('diagnosis.verify.notRecovered')
                        })
                      )
                      .join(t('diagnosis.verify.separator'))}
                    showIcon
                    style={{ marginTop: 8 }}
                  />
                )}
              </Card>
            </div>
          ))}
          {loading && (
            <Spin tip={progressText ?? t('diagnosis.progress.analyzing')}>
              <div style={{ minHeight: 48 }} />
            </Spin>
          )}
        </div>

        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={handleSend}
            placeholder={t('diagnosis.placeholder.symptom')}
            disabled={loading}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}>
            {t('diagnosis.action.diagnose')}
          </Button>
        </Space.Compact>
      </Card>
    </div>
  );
}
