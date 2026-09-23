import { Card, Button, Tag, Typography, Space, Alert } from 'antd';
import { ExclamationCircleOutlined, ToolOutlined, RollbackOutlined } from '@ant-design/icons';
import { useState, useRef, useEffect } from 'react';
import {
  executeRemedial,
  previewRemedial,
  rollbackRemedial,
  type ProposedCommand,
  type RemedialPreview
} from '@/services/diagnosis';
import { subscribeTaskProgress } from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';
import { useConfirm } from '@/utils/confirm';
import { useTranslation } from 'react-i18next';

const { Text, Paragraph } = Typography;

interface CommandConfirmCardProps {
  commands: ProposedCommand[];
  deviceId: number;
  sessionId?: number;
  onExecuted?: () => void;
}

const RISK_COLOR: Record<string, string> = {
  none: 'green',
  low: 'blue',
  medium: 'orange',
  high: 'red'
};

export default function CommandConfirmCard({
  commands,
  deviceId,
  sessionId,
  onExecuted
}: CommandConfirmCardProps) {
  const confirm = useConfirm();
  const message = useMessage();
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
  const [loading, setLoading] = useState<number | null>(null);
  const [executed, setExecuted] = useState<Record<number, boolean>>({});
  const [previewing, setPreviewing] = useState<number | null>(null);
  const sseCancelRef = useRef<{ cancel: () => void } | null>(null);

  useEffect(() => {
    return () => {
      sseCancelRef.current?.cancel();
    };
  }, []);

  if (!commands || commands.length === 0) {
    return null;
  }

  const remedialCommands = commands.filter((c) => c.type === 'remedial');
  const diagnosticCommands = commands.filter((c) => c.type === 'diagnostic');

  const renderPreview = (preview: RemedialPreview) => (
    <div>
      <Paragraph style={{ marginBottom: 4 }}>{t('command.preview.intro')}</Paragraph>
      <pre
        style={{
          background: '#f5f5f5',
          padding: 8,
          borderRadius: 4,
          marginBottom: 8,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all'
        }}
      >
        {preview.command}
      </pre>
      {/* 平台前置/后置条件：这类约束不满足时命令会"成功但不生效" */}
      {preview.platform_note && (
        <Alert
          type="warning"
          message={t('command.preview.noticeTitle')}
          description={preview.platform_note}
          showIcon
          style={{ marginBottom: 8 }}
        />
      )}
      {preview.risk === 'high' && (
        <Alert
          type="error"
          message={t('command.preview.highRiskTitle')}
          description={t('command.preview.highRiskDesc')}
          showIcon
        />
      )}
      {preview.rollback_command_key && (
        <Paragraph type="secondary" style={{ marginTop: 8 }}>
          {t('command.preview.rollbackLabel')}
          <Text code>{preview.rollback_command_key}</Text>
        </Paragraph>
      )}
    </div>
  );

  const subscribeProgress = (taskId: string, index: number) => {
    sseCancelRef.current?.cancel();
    sseCancelRef.current = subscribeTaskProgress(
      taskId,
      (event) => {
        if (event.type === 'progress') {
          return;
        }
        if (event.type === 'done') {
          message.success(t('command.message.executed'));
          setExecuted((prev) => ({ ...prev, [index]: true }));
          setLoading(null);
          onExecuted?.();
        } else if (event.type === 'error') {
          if (event.message === 'task not found') {
            message.info(t('command.message.taskFinished'));
          } else {
            message.error(
              t('command.message.execFailedHint', {
                reason: event.message || event.result || t('error.unknown')
              })
            );
          }
          setLoading(null);
        }
      },
      () => {
        message.error(t('command.message.progressDisconnected'));
        setLoading(null);
      }
    );
  };

  const handleExecute = async (cmd: ProposedCommand, index: number) => {
    setPreviewing(index);
    let preview: RemedialPreview;
    try {
      preview = await previewRemedial(deviceId, cmd.command_key, cmd.params || {});
    } catch (e) {
      message.error(t('command.message.unavailable', { reason: e instanceof Error ? e.message : String(e) }));
      return;
    } finally {
      setPreviewing(null);
    }

    const idempotencyKey =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    confirm({
      title: t('command.confirm.title'),
      icon: <ExclamationCircleOutlined />,
      width: 560,
      content: renderPreview(preview),
      okText: t('command.confirm.okText'),
      okType: 'danger',
      cancelText: tc('action.cancel'),
      onOk: async () => {
        setLoading(index);
        try {
          const resp = await executeRemedial(
            deviceId,
            cmd.command_key,
            cmd.params || {},
            sessionId,
            idempotencyKey
          );
          if (resp.duplicate) {
            if (resp.finished) {
              message.info(t('command.message.taskFinished'));
              setLoading(null);
              return;
            }
            message.info(t('command.message.duplicateReused'));
          }
          subscribeProgress(resp.task_id, index);
        } catch (e) {
          message.error(
            t('command.message.execFailed', { reason: e instanceof Error ? e.message : String(e) })
          );
          setLoading(null);
        }
      }
    });
  };

  const handleRollback = async (cmd: ProposedCommand, index: number) => {
    if (!cmd.rollback_command_key) return;
    if (!executed[index]) {
      message.warning(t('command.message.notExecutedNoRollback'));
      return;
    }
    setLoading(index);
    try {
      await rollbackRemedial(deviceId, cmd.rollback_command_key, cmd.params || {}, sessionId);
      message.success(t('command.message.rollbackSuccess'));
      setExecuted((prev) => ({ ...prev, [index]: false }));
      onExecuted?.();
    } catch (e) {
      message.error(
        t('command.message.rollbackFailed', { reason: e instanceof Error ? e.message : String(e) })
      );
    } finally {
      setLoading(null);
    }
  };

  return (
    <Card title={t('command.title')} size="small" style={{ marginTop: 12 }}>
      {diagnosticCommands.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">{t('command.diagnosticLabel')}</Text>
          <Space wrap style={{ marginTop: 4 }}>
            {diagnosticCommands.map((cmd, i) => (
              <Tag key={i} icon={<ToolOutlined />} color="blue">
                {cmd.command_key}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {remedialCommands.length > 0 && (
        <div>
          <Alert
            type="warning"
            message={t('command.alert.title')}
            description={t('command.alert.description')}
            showIcon
            style={{ marginBottom: 12 }}
          />
          {remedialCommands.map((cmd, i) => (
            <Card
              key={i}
              size="small"
              style={{ marginBottom: 8 }}
              actions={[
                <Button
                  type="primary"
                  danger={cmd.risk_level === 'high'}
                  loading={loading === i || previewing === i}
                  onClick={() => handleExecute(cmd, i)}
                  icon={<ToolOutlined />}
                >
                  {t('command.action.execute')}
                </Button>,
                cmd.rollback_command_key && (
                  <Button
                    loading={loading === i}
                    disabled={!executed[i]}
                    onClick={() => handleRollback(cmd, i)}
                    icon={<RollbackOutlined />}
                  >
                    {t('command.action.rollback')}
                  </Button>
                )
              ].filter(Boolean)}
            >
              <Card.Meta
                title={
                  <Space>
                    <Text code>{cmd.command_key}</Text>
                    <Tag color={RISK_COLOR[cmd.risk_level || 'none'] || 'default'}>
                      {cmd.risk_level || 'unknown'}
                    </Tag>
                  </Space>
                }
                description={
                  <div>
                    {cmd.params && Object.keys(cmd.params).length > 0 && (
                      <Text type="secondary">
                        {t('command.field.params', { params: JSON.stringify(cmd.params) })}
                      </Text>
                    )}
                    {cmd.rollback_command_key && (
                      <div style={{ marginTop: 4 }}>
                        <Text type="secondary">{t('command.field.rollback')}</Text>
                        <Text code>{cmd.rollback_command_key}</Text>
                      </div>
                    )}
                  </div>
                }
              />
            </Card>
          ))}
        </div>
      )}
    </Card>
  );
}
