import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Button,
  Space,
  Descriptions,
  Tag,
  Divider,
  Skeleton,
  Alert,
  Tooltip,
  Empty
} from 'antd';
import { SettingOutlined, SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { getAIConfig, updateAIConfig, type AIConfig } from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';

export default function AIConfigPage() {
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form] = Form.useForm();
  const message = useMessage();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getAIConfig();
      setConfig(data);
      form.setFieldsValue({
        provider: data.provider,
        base_url: data.base_url,
        model: data.model,
        timeout: data.timeout,
        stream_timeout: data.stream_timeout,
        max_tokens: data.max_tokens,
        temperature: data.temperature
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载配置失败';
      setLoadError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [form, message]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const updates = { ...values };
      if (!updates.api_key) {
        delete updates.api_key;
      }
      setSaving(true);
      const result = await updateAIConfig(updates);
      setConfig(result);
      message.success(`已更新: ${result.changed.join(', ')}`);
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return;
      }
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      title={
        <Space>
          <SettingOutlined />
          <span>AI 配置管理</span>
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={fetchConfig} loading={loading}>
          刷新
        </Button>
      }
    >
      {/* F7 修复：原实现在加载中/加载失败时 `config` 为 null，页面只剩 Card 标题、
          内容区全空白，用户无法区分"还在加载"和"加载失败"。补 Skeleton + 错误态 + 重试。 */}
      {loadError && (
        <Alert
          type="error"
          showIcon
          message="加载配置失败"
          description={loadError}
          action={
            <Button size="small" onClick={fetchConfig}>
              重试
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}
      {!loadError && (
        <Skeleton loading={loading} active paragraph={{ rows: 6 }}>
          {config && (
            <>
              <Descriptions
                column={{ xs: 1, sm: 1, md: 2 }}
                size="small"
                bordered
                style={{ marginBottom: 24 }}
              >
                <Descriptions.Item label="API Key 状态">
                  <Space size={4} wrap>
                    {config.api_key_configured ? (
                      <Tag color="green">已配置</Tag>
                    ) : (
                      <Tag color="red">未配置</Tag>
                    )}
                    {/* F13 修复：后端已返回 api_key_local_only，此前前端未展示。
                    为 true 表示"其他 worker 进程配过 key，但当前进程未同步"
                    （api_key 不落 Redis 故无法跨 worker 同步）。
                    若不展示，多 worker 下页面显示"已配置✅"，会掩盖
                    "当前进程实际无 key"的真实故障。 */}
                    {config.api_key_local_only && (
                      <Tooltip title="api_key 不跨进程同步。其他 worker 已配置，但处理本次请求的进程未生效，需重启该进程或改用环境变量注入。">
                        <Tag color="orange">本进程未同步</Tag>
                      </Tooltip>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="API Key（脱敏）">
                  {config.api_key_masked || <Tag>空</Tag>}
                </Descriptions.Item>
              </Descriptions>

              <Form form={form} layout="vertical">
                <Form.Item
                  label="Provider"
                  name="provider"
                  rules={[{ required: true }]}
                  tooltip="OpenAI 兼容协议（DeepSeek/通义千问/Ollama 等）统一填 openai，通过下方 Base URL 切换端点。填错未注册的 provider 会被后端拒绝。"
                  extra={
                    <span style={{ fontSize: 12, color: '#8c8c8c' }}>
                      兼容服务示例：openai（官方/DeepSeek <code>https://api.deepseek.com/v1</code> /
                      通义 <code>https://dashscope.aliyuncs.com/compatible-mode/v1</code> / Ollama{' '}
                      <code>http://localhost:11434/v1</code>）
                    </span>
                  }
                >
                  <Input placeholder="openai" />
                </Form.Item>
                <Form.Item label="API Base URL" name="base_url" rules={[{ required: true }]}>
                  <Input placeholder="https://api.openai.com/v1" />
                </Form.Item>
                <Form.Item label="模型" name="model" rules={[{ required: true }]}>
                  <Input placeholder="gpt-4o-mini" />
                </Form.Item>
                <Form.Item label="API Key（留空不修改）" name="api_key">
                  <Input.Password placeholder="输入新 Key 以更新，留空保持不变" />
                </Form.Item>
                <Space size="large" style={{ display: 'flex' }}>
                  <Form.Item label="请求超时（秒）" name="timeout" style={{ flex: 1 }}>
                    <InputNumber min={1} max={300} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item label="流式超时（秒）" name="stream_timeout" style={{ flex: 1 }}>
                    <InputNumber min={1} max={600} style={{ width: '100%' }} />
                  </Form.Item>
                </Space>
                <Space size="large" style={{ display: 'flex' }}>
                  <Form.Item label="最大 Token" name="max_tokens" style={{ flex: 1 }}>
                    <InputNumber min={1} max={8192} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item label="温度" name="temperature" style={{ flex: 1 }}>
                    <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
                  </Form.Item>
                </Space>
                <Divider />
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={handleSave}
                  loading={saving}
                >
                  保存配置
                </Button>
              </Form>
            </>
          )}
          {/* 加载完成但无数据（后端异常返回空）时给出空态，而非空白 */}
          {!loading && !loadError && !config && <Empty description="暂无配置数据" />}
        </Skeleton>
      )}
    </Card>
  );
}
