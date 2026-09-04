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
import { confirm } from '@/utils/confirm';

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
  const message = useMessage();
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
      <Paragraph style={{ marginBottom: 4 }}>即将在设备上执行：</Paragraph>
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
          message="执行前须知"
          description={preview.platform_note}
          showIcon
          style={{ marginBottom: 8 }}
        />
      )}
      {preview.risk === 'high' && (
        <Alert
          type="error"
          message="高危操作"
          description="此命令风险等级为 high，执行前已自动备份 running-config，失败将自动回滚。"
          showIcon
        />
      )}
      {preview.rollback_command_key && (
        <Paragraph type="secondary" style={{ marginTop: 8 }}>
          回滚命令：<Text code>{preview.rollback_command_key}</Text>
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
          message.success('命令执行完成');
          setExecuted((prev) => ({ ...prev, [index]: true }));
          setLoading(null);
          onExecuted?.();
        } else if (event.type === 'error') {
          if (event.message === 'task not found') {
            message.info('任务已完成，请刷新状态');
          } else {
            message.error(
              `执行失败：${event.message || event.result || '未知错误'}（如为临时故障，请重试）`
            );
          }
          setLoading(null);
        }
      },
      () => {
        message.error('进度订阅断开，请检查网络');
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
      message.error(`命令不可用：${e instanceof Error ? e.message : String(e)}`);
      return;
    } finally {
      setPreviewing(null);
    }

    const idempotencyKey =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    confirm({
      title: '确认执行修复命令',
      icon: <ExclamationCircleOutlined />,
      width: 560,
      content: renderPreview(preview),
      okText: '确认执行',
      okType: 'danger',
      cancelText: '取消',
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
              message.info('任务已完成，请刷新状态');
              setLoading(null);
              return;
            }
            message.info('检测到重复请求，已复用首次任务');
          }
          subscribeProgress(resp.task_id, index);
        } catch (e) {
          message.error(`执行失败：${e instanceof Error ? e.message : String(e)}`);
          setLoading(null);
        }
      }
    });
  };

  const handleRollback = async (cmd: ProposedCommand, index: number) => {
    if (!cmd.rollback_command_key) return;
    if (!executed[index]) {
      message.warning('该命令尚未执行，无需回滚');
      return;
    }
    setLoading(index);
    try {
      await rollbackRemedial(deviceId, cmd.rollback_command_key, cmd.params || {}, sessionId);
      message.success('回滚成功');
      setExecuted((prev) => ({ ...prev, [index]: false }));
      onExecuted?.();
    } catch (e) {
      message.error(`回滚失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(null);
    }
  };

  return (
    <Card title="待确认命令" size="small" style={{ marginTop: 12 }}>
      {diagnosticCommands.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">诊断命令（只读，可安全执行）：</Text>
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
            message="修复命令需人工确认"
            description="以下命令将变更设备配置，执行前已自动备份。高危命令失败将自动回滚。"
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
                  执行
                </Button>,
                cmd.rollback_command_key && (
                  <Button
                    loading={loading === i}
                    disabled={!executed[i]}
                    onClick={() => handleRollback(cmd, i)}
                    icon={<RollbackOutlined />}
                  >
                    回滚
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
                      <Text type="secondary">参数：{JSON.stringify(cmd.params)}</Text>
                    )}
                    {cmd.rollback_command_key && (
                      <div style={{ marginTop: 4 }}>
                        <Text type="secondary">回滚：</Text>
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
