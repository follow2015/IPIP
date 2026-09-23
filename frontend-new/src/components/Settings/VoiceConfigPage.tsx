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
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

type RequiredFieldLabelKey =
  | 'voice.field.accessKeyId'
  | 'voice.field.accessKeySecret'
  | 'voice.field.voiceTemplateId'
  | 'voice.field.secretId'
  | 'voice.field.secretKey'
  | 'voice.field.sdkAppId';

const REQUIRED_FIELDS: Record<
  'aliyun' | 'tencent',
  Array<{ key: string; labelKey: RequiredFieldLabelKey }>
> = {
  aliyun: [
    { key: 'aliyun_access_key_id', labelKey: 'voice.field.accessKeyId' },
    { key: 'aliyun_access_key_secret', labelKey: 'voice.field.accessKeySecret' },
    { key: 'aliyun_tts_code', labelKey: 'voice.field.voiceTemplateId' }
  ],
  tencent: [
    { key: 'tencent_secret_id', labelKey: 'voice.field.secretId' },
    { key: 'tencent_secret_key', labelKey: 'voice.field.secretKey' },
    { key: 'tencent_app_id', labelKey: 'voice.field.sdkAppId' },
    { key: 'tencent_template_id', labelKey: 'voice.field.voiceTemplateId' }
  ]
};

const VoiceConfigPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { t: tCommon } = useTranslation('common');
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
        messageApi.success(t('voice.message.saved'));
        setEditing(false);
      } catch {
        messageApi.error(t('saveFailed'));
      }
    },
    [updateMutation, messageApi, t]
  );

  const handleTest = useCallback(async () => {
    const values = form.getFieldsValue();
    try {
      const res = await testMutation.mutateAsync(values as VoiceConfigUpdate);
      if (res.success) {
        messageApi.success(res.message || t('voice.message.testStarted'));
      } else {
        messageApi.error(res.message || t('voice.message.testFailed'));
      }
    } catch {
      messageApi.error(t('voice.message.testFailedCheckConfig'));
    }
  }, [form, testMutation, messageApi, t]);

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    );
  }

  const providerOptions = [
    { value: 'aliyun', label: t('voice.providerOption.aliyun') },
    { value: 'tencent', label: t('voice.providerOption.tencent') }
  ];

  const verifyModeOptions = [
    {
      value: 'ip_only',
      label: (
        <Tooltip title={t('voice.verifyModeOption.ipOnlyTooltip')}>
          {t('voice.verifyModeOption.ipOnly')}
        </Tooltip>
      )
    },
    {
      value: 'signature_and_ip',
      label: (
        <Tooltip title={t('voice.verifyModeOption.signatureAndIpTooltip')}>
          {t('voice.verifyModeOption.signatureAndIp')}
        </Tooltip>
      )
    },
    { value: 'off', label: t('voice.verifyModeOption.off') }
  ];

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
            <span>{t('voice.title')}</span>
          </Space>
        }
        extra={
          <Space>
            {ready ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                {t('voice.tagReady')}
              </Tag>
            ) : (
              <Tag icon={<CloseCircleOutlined />} color="warning">
                {t('voice.tagNotReady')}
              </Tag>
            )}
            {!editing && (
              <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                {tCommon('action.edit')}
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
                ? t('voice.alert.notReady', {
                    fields:
                      missingFields
                        .map((key) => {
                          const field = requiredList.find((f) => f.key === key);
                          return field ? t(field.labelKey) : key;
                        })
                        .join(t('voice.listSeparator')) || t('voice.alert.requiredFields')
                  })
                : t('voice.alert.disabledHint')
            }
          />
        )}

        <Form form={form} layout="vertical" onFinish={handleSave} disabled={!editing}>
          {/* ── 总开关 ─────────────────────────────────────────── */}
          <Form.Item
            label={
              <Space>
                <SoundOutlined />
                {t('voice.masterSwitch')}
              </Space>
            }
            name="enabled"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -12, marginBottom: 16, display: 'block' }}>
            {t('voice.masterSwitchHint')}
          </Text>

          <Divider />

          {/* ── 服务商 ─────────────────────────────────────────── */}
          <Title level={5}>{t('voice.section.provider')}</Title>
          <Form.Item label={t('voice.section.provider')} name="provider">
            <Select
              options={providerOptions}
              onChange={(v) => setProvider(v as 'aliyun' | 'tencent')}
              disabled={!editing}
            />
          </Form.Item>

          {/* ── 阿里云 ─────────────────────────────────────────── */}
          {provider === 'aliyun' && (
            <>
              <Form.Item label={t('voice.field.accessKeyId')} name="aliyun_access_key_id">
                <Input
                  placeholder={t('voice.field.accessKeyIdPlaceholder')}
                  autoComplete="off"
                />
              </Form.Item>
              <Form.Item
                label={
                  <Space>
                    <LockOutlined />
                    {t('voice.field.accessKeySecret')}
                  </Space>
                }
                name="aliyun_access_key_secret"
              >
                <Input.Password
                  placeholder={t('voice.field.configuredPlaceholder')}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title={t('voice.field.callerNumberTooltip')}>
                    {t('voice.field.callerNumber')}
                    <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                  </Tooltip>
                }
                name="aliyun_caller_number"
              >
                <Input placeholder={t('voice.field.callerNumberPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('voice.field.ttsCode')} name="aliyun_tts_code">
                <Input placeholder={t('voice.field.ttsCodePlaceholder')} />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title={t('voice.field.ttsParamTooltip')}>
                    {t('voice.field.ttsParam')}
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
                        return Promise.reject(new Error(t('voice.validation.invalidJson')));
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
              <Form.Item label={t('voice.field.secretId')} name="tencent_secret_id">
                <Input placeholder={t('voice.field.secretIdPlaceholder')} autoComplete="off" />
              </Form.Item>
              <Form.Item
                label={
                  <Space>
                    <LockOutlined />
                    {t('voice.field.secretKey')}
                  </Space>
                }
                name="tencent_secret_key"
              >
                <Input.Password
                  placeholder={t('voice.field.configuredPlaceholder')}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Form.Item
                label={
                  <Tooltip title={t('voice.field.sdkAppIdTooltip')}>
                    {t('voice.field.sdkAppId')}
                    <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                  </Tooltip>
                }
                name="tencent_app_id"
              >
                <Input placeholder={t('voice.field.sdkAppIdPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('voice.field.templateId')} name="tencent_template_id">
                <Input placeholder={t('voice.field.templateIdPlaceholder')} />
              </Form.Item>
            </>
          )}

          <Divider />

          {/* ── 通用参数 ───────────────────────────────────────── */}
          <Title level={5}>{t('voice.section.common')}</Title>
          <Space size="large" wrap>
            <Form.Item
              label={
                <Tooltip title={t('voice.field.playTimesTooltip')}>
                  {t('voice.field.playTimes')}
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
                    <Tooltip title={t('voice.field.volumeTooltip')}>
                      {t('voice.field.volume')}
                      <QuestionCircleOutlined style={{ marginLeft: 4 }} />
                    </Tooltip>
                  }
                  name="volume"
                >
                  <InputNumber min={0} max={100} />
                </Form.Item>
                <Form.Item
                  label={
                    <Tooltip title={t('voice.field.speedTooltip')}>
                      {t('voice.field.speed')}
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
                <Tooltip title={t('voice.field.callTimeoutTooltip')}>
                  {t('voice.field.callTimeout')}
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
              message={t('voice.alert.tencentNoVolumeSpeed')}
            />
          )}

          <Divider />

          {/* ── 回调安全 ───────────────────────────────────────── */}
          <Title level={5}>
            <SafetyOutlined style={{ marginRight: 8 }} />
            {t('voice.section.callbackSecurity')}
          </Title>
          <Form.Item label={t('voice.field.verifyMode')} name="callback_verify_mode">
            <Select options={verifyModeOptions} />
          </Form.Item>
          <Form.Item
            label={
              <Space>
                <LockOutlined />
                {t('voice.field.callbackToken')}
              </Space>
            }
            name="callback_token"
          >
            <Input.Password
              placeholder={t('voice.field.configuredPlaceholder')}
              autoComplete="new-password"
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={t('voice.callbackUrlHint')}
          />

          {editing && (
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                  {t('saveConfig')}
                </Button>
                <Button
                  onClick={() => {
                    setEditing(false);
                    if (config) initFormValues(config);
                  }}
                >
                  {tCommon('action.cancel')}
                </Button>
              </Space>
            </Form.Item>
          )}
        </Form>

        <Divider />

        {/* ── 测试呼叫 ─────────────────────────────────────────── */}
        <Title level={5}>{t('voice.section.testCall')}</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          {t('voice.test.hint')}
        </Text>
        <Button
          icon={<PhoneOutlined />}
          loading={testMutation.isPending}
          onClick={handleTest}
          disabled={!status?.enabled}
        >
          {t('voice.test.submit')}
        </Button>
      </Card>
    </>
  );
};

export default VoiceConfigPage;
