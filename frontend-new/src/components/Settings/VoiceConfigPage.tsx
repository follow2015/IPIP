import React, { useCallback, useEffect, useState } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Button,
  Space,
  Typography,
  Divider,
  message,
  Alert,
  Tooltip,
  Descriptions,
  Tag,
  Select,
  Switch,
  Spin
} from 'antd';
import {
  PhoneOutlined,
  QuestionCircleOutlined,
  LockOutlined,
  EditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SoundOutlined,
  SafetyOutlined
} from '@ant-design/icons';
import {
  useVoiceConfig,
  useVoiceChannelStatus,
  useUpdateVoiceConfig,
  useTestVoiceCall,
  type VoiceConfig,
  type VoiceConfigUpdate
} from '@/services/voice-settings';

const { Title, Text } = Typography;

const PROVIDER_OPTIONS = [
  { value: 'aliyun', label: '阿里云（SingleCallByTts）' },
  { value: 'tencent', label: '腾讯云（SendTtsVoice）' }
];

const VERIFY_MODE_OPTIONS = [
  {
    value: 'ip_only',
    label: (
      <Tooltip title="仅校验回调来源 IP 白名单。两家官方语音回调均不携带自定义签名头，推荐先用此模式验证连通性">
        仅 IP 白名单（推荐）
      </Tooltip>
    )
  },
  {
    value: 'signature_and_ip',
    label: (
      <Tooltip title="签名 + IP 双重校验。需厂商支持自定义签名头，否则回调会被 100% 拒收">
        签名 + IP 白名单
      </Tooltip>
    )
  },
  { value: 'off', label: '关闭校验（不推荐）' }
];

const REQUIRED_FIELDS: Record<string, Array<{ key: string; label: string }>> = {
  aliyun: [
    { key: 'aliyun_access_key_id', label: 'AccessKey ID' },
    { key: 'aliyun_access_key_secret', label: 'AccessKey Secret' },
    { key: 'aliyun_tts_code', label: '语音模板 ID' }
  ],
  tencent: [
    { key: 'tencent_secret_id', label: 'SecretId' },
    { key: 'tencent_secret_key', label: 'SecretKey' },
    { key: 'tencent_app_id', label: 'VoiceSdkAppid' },
    { key: 'tencent_template_id', label: '语音模板 ID' }
  ]
};

const VoiceConfigPage: React.FC = () => {
  const { data: config, isLoading } = useVoiceConfig();
  const { data: status } = useVoiceChannelStatus();
  const updateMutation = useUpdateVoiceConfig();
  const testMutation = useTestVoiceCall();
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [provider, setProvider] = useState<'aliyun' | 'tencent'>('aliyun');
  const [editing, setEditing] = useState(false);

  const initFormValues = useCallback(
    (cfg: VoiceConfig) => {
      setProvider(cfg.provider);
      form.setFieldsValue({
        provider: cfg.provider,
        aliyun_access_key_id: cfg.aliyun_access_key_id,
        aliyun_access_key_secret: cfg.aliyun_access_key_secret_set ? '****' : '',
        aliyun_caller_number: cfg.aliyun_caller_number,
        aliyun_tts_code: cfg.aliyun_tts_code,
        aliyun_tts_param: cfg.aliyun_tts_param,
        tencent_secret_id: cfg.tencent_secret_id,
        tencent_secret_key: cfg.tencent_secret_key_set ? '****' : '',
        tencent_app_id: cfg.tencent_app_id,
        tencent_template_id: cfg.tencent_template_id,
        play_times: cfg.play_times,
        volume: cfg.volume,
        speed: cfg.speed,
        call_timeout: cfg.call_timeout,
        callback_token: cfg.callback_token_set ? '****' : '',
        callback_verify_mode: cfg.callback_verify_mode,
        enabled: cfg.enabled
      });
    },
    [form]
  );

  useEffect(() => {
    if (config) {
      initFormValues(config);
    }
  }, [config, initFormValues]);

  const handleSave = useCallback(
    async (values: Record<string, unknown>) => {
      const update: VoiceConfigUpdate = { ...values };
      try {
        await updateMutation.mutateAsync(update);
        messageApi.success('语音配置已保存');
        setEditing(false);
      } catch {
        messageApi.error('保存失败，请重试');
      }
    },
    [updateMutation, messageApi]
  );

  const handleTest = useCallback(async () => {
    const values = form.getFieldsValue();
    try {
      const res = await testMutation.mutateAsync(values as VoiceConfigUpdate);
      if (res.success) {
        messageApi.success(res.message || '测试呼叫已发起，请留意手机');
      } else {
        messageApi.error(res.message || '测试呼叫失败');
      }
    } catch {
      messageApi.error('测试呼叫失败，请检查配置');
    }
  }, [form, testMutation, messageApi]);

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    );
  }

  const requiredList = REQUIRED_FIELDS[provider] ?? [];
  const missingFields = status?.missing ?? [];
  const ready = status?.ready ?? false;

  return (
    <>
      {contextHolder}
      <Card
        title={
          <Space>
            <PhoneOutlined />
            <span>语音通知配置</span>
          </Space>
        }
        extra={
          <Space>
            {ready ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                就绪
              </Tag>
            ) : (
              <Tag icon={<CloseCircleOutlined />} color="warning">
                未就绪
              </Tag>
            )}
            {!editing && (
              <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                编辑
              </Button>
            )}
          </Space>
        }
        style={{ maxWidth: 760 }}
      >
        {!ready && status && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message={
              status.enabled
                ? `配置未就绪，缺少：${
                    missingFields
                      .map((key) => requiredList.find((f) => f.key === key)?.label ?? key)
                      .join('、') || '必填项'
                  }`
                : '语音通知未启用，请开启总开关并补全服务商配置'
            }
          />
        )}

        <Form form={form} layout="vertical" onFinish={handleSave} disabled={!editing}>
          {/* ── 总开关 ─────────────────────────────────────────── */}
          <Form.Item
            label={
              <Space>
                <SoundOutlined />
                启用语音通知
              </Space>
            }
            name="enabled"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -12, marginBottom: 16, display: 'block' }}>
            总开关关闭时，即使个别用户开启了语音偏好也不会外呼
          </Text>

          <Divider />

          {/* ── 服务商 ─────────────────────────────────────────── */}
          <Title level={5}>服务商</Title>
          <Form.Item label="服务商" name="provider">
            <Select
              options={PROVIDER_OPTIONS}
              onChange={(v) => setProvider(v as 'aliyun' | 'tencent')}
              disabled={!editing}
            />
          </Form.Item>

          {/* ── 阿里云 ─────────────────────────────────────────── */}
          {provider === 'aliyun' && (
            <>
              <Form.Item label="AccessKey ID" name="aliyun_access_key_id">
                <Input placeholder="LTAI..." autoComplete="off" />
              </Form.Item>
              <Form.Item
                label={
                  <Space>
                    <LockOutlined />
                    AccessKey Secret
                  </Space>
                }
                name="aliyun_access_key_secret"
              >
                <Input.Password placeholder="已配置则显示 ****" autoComplete="new-password" />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title="留空 = 公共模式（公共号池外呼，无需报备）；填写真实报备号码 = 专属模式。公共模式必须留空，误填未报备号码会导致呼叫失败">
                    主叫号码（选填）
                    <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                  </Tooltip>
                }
                name="aliyun_caller_number"
              >
                <Input placeholder="公共模式请留空" />
              </Form.Item>
              <Form.Item label="语音模板 ID（TtsCode）" name="aliyun_tts_code">
                <Input placeholder="TTS_xxxxxx" />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title="模板变量映射，JSON 对象。运行时会叠加动态变量 title（告警标题）与 level（级别）">
                    模板变量（JSON）
                    <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                  </Tooltip>
                }
                name="aliyun_tts_param"
                rules={[
                  {
                    validator: (_, value) => {
                      if (!value) return Promise.resolve();
                      try {
                        JSON.parse(value);
                        return Promise.resolve();
                      } catch {
                        return Promise.reject(new Error('必须是合法 JSON'));
                      }
                    }
                  }
                ]}
              >
                <Input placeholder='{"company":"XX"}' />
              </Form.Item>
            </>
          )}

          {/* ── 腾讯云 ─────────────────────────────────────────── */}
          {provider === 'tencent' && (
            <>
              <Form.Item label="SecretId" name="tencent_secret_id">
                <Input placeholder="AKID..." autoComplete="off" />
              </Form.Item>
              <Form.Item
                label={
                  <Space>
                    <LockOutlined />
                    SecretKey
                  </Space>
                }
                name="tencent_secret_key"
              >
                <Input.Password placeholder="已配置则显示 ****" autoComplete="new-password" />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title="语音应用 SDKAppID，腾讯云必填">
                    VoiceSdkAppid
                    <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                  </Tooltip>
                }
                name="tencent_app_id"
              >
                <Input placeholder="140xxxxxxx" />
              </Form.Item>
              <Form.Item label="语音模板 ID（TemplateId）" name="tencent_template_id">
                <Input placeholder="模板 ID" />
              </Form.Item>
            </>
          )}

          <Divider />

          {/* ── 通用参数 ───────────────────────────────────────── */}
          <Title level={5}>通用参数</Title>
          <Space size="large" wrap>
            <Form.Item
              label={
                <Tooltip title="同一通语音重复播放次数（1~3）">
                  播放次数
                  <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                </Tooltip>
              }
              name="play_times"
            >
              <InputNumber min={1} max={3} />
            </Form.Item>
            {provider === 'aliyun' && (
              <>
                <Form.Item
                  label={
                    <Tooltip title="音量 0~100，腾讯云不支持">
                      音量
                      <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                    </Tooltip>
                  }
                  name="volume"
                >
                  <InputNumber min={0} max={100} />
                </Form.Item>
                <Form.Item
                  label={
                    <Tooltip title="语速 -500~500，腾讯云不支持">
                      语速
                      <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                    </Tooltip>
                  }
                  name="speed"
                >
                  <InputNumber min={-500} max={500} />
                </Form.Item>
              </>
            )}
            <Form.Item
              label={
                <Tooltip title="呼叫超时秒数（10~30）。硬上限 30 秒，为后台任务软超时预留余量">
                  呼叫超时（秒）
                  <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                </Tooltip>
              }
              name="call_timeout"
            >
              <InputNumber min={10} max={30} />
            </Form.Item>
          </Space>
          {provider === 'tencent' && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="腾讯云 VMS 不支持音量 / 语速参数"
            />
          )}

          <Divider />

          {/* ── 回调安全 ───────────────────────────────────────── */}
          <Title level={5}>
            <SafetyOutlined style={{ marginRight: 8 }} />
            回调安全
          </Title>
          <Form.Item label="回调校验模式" name="callback_verify_mode">
            <Select options={VERIFY_MODE_OPTIONS} />
          </Form.Item>
          <Form.Item
            label={
              <Space>
                <LockOutlined />
                回调 Token
              </Space>
            }
            name="callback_token"
          >
            <Input.Password placeholder="已配置则显示 ****" autoComplete="new-password" />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="服务商回调地址：https://<你的域名>/api/notification/voice/callback（免登，需加入网关白名单）"
          />

          {editing && (
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                  保存配置
                </Button>
                <Button
                  onClick={() => {
                    setEditing(false);
                    if (config) initFormValues(config);
                  }}
                >
                  取消
                </Button>
              </Space>
            </Form.Item>
          )}
        </Form>

        <Divider />

        {/* ── 测试呼叫 ─────────────────────────────────────────── */}
        <Title level={5}>测试呼叫</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          向当前管理员账号的手机号发起一次测试呼叫（需先在个人资料中设置手机号）。
          测试会使用上方表单当前值，包括尚未保存的修改。
        </Text>
        <Button
          icon={<PhoneOutlined />}
          loading={testMutation.isPending}
          onClick={handleTest}
          disabled={!status?.enabled}
        >
          发起测试呼叫
        </Button>
      </Card>
    </>
  );
};

export default VoiceConfigPage;
