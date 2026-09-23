/**
 * MailConfigPage — 邮件服务器配置管理页面
 *
 * 仅管理员可见。支持查看已保存配置、编辑、删除（重置）、连通性测试。
 * 三种视图状态：未配置 → 配置表单；已配置 → 查看卡片 → 编辑表单。
 * 测试邮件时弹出 Modal 填写收件人地址。
 */
import React, { useCallback, useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
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
  Modal
} from 'antd';
import { useConfirm } from '@/utils/confirm';
import {
  MailOutlined,
  SendOutlined,
  QuestionCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import {
  useMailConfig,
  useUpdateMailConfig,
  useDeleteMailConfig,
  useTestMailConfig,
  type MailConfig,
  type MailConfigUpdate
} from '@/services/mail-settings';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

const SSL_MODE_MAP = {
  tls: { labelKey: 'mail.encryption.tls', color: 'blue' },
  ssl: { labelKey: 'mail.encryption.ssl', color: 'green' },
  none: { labelKey: 'mail.encryption.none', color: 'default' }
} as const;

type ProviderKey =
  | 'tencentExmail'
  | 'aliyunExmail'
  | 'qq'
  | 'netease163'
  | 'gmail'
  | 'sendgrid';

const PROVIDERS: Array<{
  labelKey: ProviderKey;
  server: string;
  port: number;
  mode: 'tls' | 'ssl' | 'none';
}> = [
  { labelKey: 'tencentExmail', server: 'smtp.exmail.qq.com', port: 465, mode: 'ssl' },
  { labelKey: 'aliyunExmail', server: 'smtp.qiye.aliyun.com', port: 465, mode: 'ssl' },
  { labelKey: 'qq', server: 'smtp.qq.com', port: 465, mode: 'ssl' },
  { labelKey: 'netease163', server: 'smtp.163.com', port: 465, mode: 'ssl' },
  { labelKey: 'gmail', server: 'smtp.gmail.com', port: 587, mode: 'tls' },
  { labelKey: 'sendgrid', server: 'smtp.sendgrid.net', port: 587, mode: 'tls' }
];

const MailConfigPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const { data: config, isLoading } = useMailConfig();
  const updateMutation = useUpdateMailConfig();
  const deleteMutation = useDeleteMailConfig();
  const testMutation = useTestMailConfig();
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [sslMode, setSslMode] = useState<'tls' | 'ssl' | 'none'>('tls');
  const [editing, setEditing] = useState(false);
  const testModalDisclosure = useDisclosure();

  const hasConfig = config && config.mail_server;

  const initFormValues = useCallback(
    (cfg: MailConfig) => {
      const mode = cfg.mail_use_ssl ? 'ssl' : cfg.mail_use_tls ? 'tls' : 'none';
      setSslMode(mode);
      form.setFieldsValue({
        mail_server: cfg.mail_server,
        mail_port: cfg.mail_port,
        ssl_mode: mode,
        mail_username: cfg.mail_username,
        mail_password: cfg.mail_password_set ? '****' : '',
        mail_default_sender: cfg.mail_default_sender,
        mail_timeout: cfg.mail_timeout
      });
    },
    [form]
  );

  React.useEffect(() => {
    if (config) {
      initFormValues(config);
    }
  }, [config, initFormValues]);

  const handleSave = useCallback(
    async (values: {
      mail_server: string;
      mail_port: number;
      ssl_mode: 'tls' | 'ssl' | 'none';
      mail_username: string;
      mail_password: string;
      mail_default_sender: string;
      mail_timeout: number;
    }) => {
      const update: MailConfigUpdate = {
        mail_server: values.mail_server,
        mail_port: values.mail_port,
        mail_use_tls: values.ssl_mode === 'tls',
        mail_use_ssl: values.ssl_mode === 'ssl',
        mail_username: values.mail_username,
        mail_password: values.mail_password,
        mail_default_sender: values.mail_default_sender,
        mail_timeout: values.mail_timeout
      };
      try {
        await updateMutation.mutateAsync(update);
        messageApi.success(t('mail.message.saved'));
        setEditing(false);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : t('saveFailed');
        messageApi.error(msg);
      }
    },
    [updateMutation, messageApi, t]
  );

  const handleDelete = useCallback(async () => {
    try {
      await deleteMutation.mutateAsync();
      messageApi.success(t('mail.message.deleted'));
      setEditing(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('mail.message.deleteFailed');
      messageApi.error(msg);
    }
  }, [deleteMutation, messageApi, t]);

  const openTestModal = useCallback(() => {
    testForm.resetFields();
    testModalDisclosure.open();
  }, [testForm]);

  const handleTestSend = useCallback(async () => {
    try {
      const values = await testForm.validateFields();
      const result = await testMutation.mutateAsync({ recipient: values.recipient });
      if (result.success) {
        messageApi.success(result.message);
        testModalDisclosure.close();
      } else {
        messageApi.error(result.message);
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        messageApi.error((err as { message: string }).message || t('testRequestFailed'));
      }
    }
  }, [testMutation, testForm, messageApi, t]);

  const handleEdit = useCallback(() => {
    if (config) {
      initFormValues(config);
    }
    setEditing(true);
  }, [config, initFormValues]);

  const handleCancelEdit = useCallback(() => {
    if (config) {
      initFormValues(config);
    }
    setEditing(false);
  }, [config, initFormValues]);

  if (isLoading) {
    return <Card loading style={{ maxWidth: 720 }} />;
  }

  const testModal = (
    <Modal
      title={t('mail.test.modalTitle')}
      open={testModalDisclosure.isOpen}
      onOk={handleTestSend}
      onCancel={() => testModalDisclosure.close()}
      okText={t('mail.action.send')}
      cancelText={tCommon('action.cancel')}
      confirmLoading={testMutation.isPending}
      destroyOnClose
    >
      <Form form={testForm} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="recipient"
          label={t('mail.test.recipient')}
          rules={[
            { required: true, message: t('mail.validation.recipientRequired') },
            { type: 'email', message: t('mail.validation.emailInvalid') }
          ]}
        >
          <Input
            placeholder={t('mail.test.recipientPlaceholder')}
            prefix={<MailOutlined />}
          />
        </Form.Item>
      </Form>
      <Alert
        type="info"
        showIcon
        message={t('mail.test.hint')}
        style={{ marginTop: 8 }}
      />
    </Modal>
  );

  if (hasConfig && !editing) {
    const mode = config.mail_use_ssl ? 'ssl' : config.mail_use_tls ? 'tls' : 'none';
    const modeInfo = SSL_MODE_MAP[mode];

    return (
      <>
        {contextHolder}
        {testModal}
        <Card style={{ maxWidth: 720 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 16
            }}
          >
            <Space>
              <MailOutlined style={{ fontSize: 18 }} />
              <Title level={5} style={{ margin: 0 }}>
                {t('mail.title')}
              </Title>
              <Tag color="green" icon={<CheckCircleOutlined />}>
                {t('mail.tagConfigured')}
              </Tag>
            </Space>
            <Space>
              <Button type="primary" icon={<SendOutlined />} onClick={openTestModal}>
                {t('mail.action.sendTest')}
              </Button>
              <Button icon={<EditOutlined />} onClick={handleEdit}>
                {tCommon('action.edit')}
              </Button>
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={deleteMutation.isPending}
                onClick={() =>
                  confirm({
                    title: t('mail.action.deleteConfirmTitle'),
                    content: t('mail.action.deleteConfirmContent'),
                    okText: tCommon('confirm.deleteTitle'),
                    cancelText: tCommon('action.cancel'),
                    okButtonProps: { danger: true },
                    onOk: handleDelete
                  })
                }
              >
                {tCommon('action.delete')}
              </Button>
            </Space>
          </div>

          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
            message={t('mail.takeEffectHint')}
          />

          <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
            <Descriptions.Item label={t('mail.descriptions.server')}>
              {config.mail_server}
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.port')}>
              {config.mail_port}
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.encryption')}>
              <Tag color={modeInfo.color}>{t(modeInfo.labelKey)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.timeoutView')}>
              {t('mail.field.timeoutValue', { seconds: config.mail_timeout })}
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.username')}>
              {config.mail_username}
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.passwordView')}>
              {config.mail_password_set ? (
                <Text type="secondary">••••••••</Text>
              ) : (
                <Tag color="warning" icon={<CloseCircleOutlined />}>
                  {t('mail.field.passwordUnset')}
                </Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('mail.field.sender')} span={2}>
              {config.mail_default_sender}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </>
    );
  }

  return (
    <>
      {contextHolder}
      {testModal}
      <Card style={{ maxWidth: 720 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16
          }}
        >
          <Space>
            <MailOutlined style={{ fontSize: 18 }} />
            <Title level={5} style={{ margin: 0 }}>
              {hasConfig ? t('mail.editTitle') : t('mail.createTitle')}
            </Title>
            {hasConfig && <Tag color="blue">{t('mail.tagEditing')}</Tag>}
          </Space>
          <Space>
            {hasConfig && <Button onClick={handleCancelEdit}>{tCommon('action.cancel')}</Button>}
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
          message={t('mail.takeEffectHint')}
        />

        <Form form={form} layout="vertical" onFinish={handleSave}>
          {/* ─── 服务器连接 ──────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            {t('mail.section.connection')}
          </Title>

          <Form.Item
            label={t('mail.field.server')}
            name="mail_server"
            rules={[{ required: true, message: t('mail.validation.serverRequired') }]}
          >
            <Input placeholder={t('mail.field.serverPlaceholder')} />
          </Form.Item>

          <Space size={16} style={{ width: '100%' }} align="start">
            <Form.Item
              label={t('mail.field.port')}
              name="mail_port"
              rules={[{ required: true, message: t('mail.validation.portRequired') }]}
              style={{ width: 120, marginBottom: 24 }}
            >
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              label={
                <Space size={4}>
                  <span>{t('mail.field.encryption')}</span>
                  <Tooltip title={t('mail.field.encryptionTooltip')}>
                    <QuestionCircleOutlined style={{ color: '#999' }} />
                  </Tooltip>
                </Space>
              }
              name="ssl_mode"
              rules={[{ required: true, message: t('mail.validation.encryptionRequired') }]}
              style={{ width: 200, marginBottom: 24 }}
            >
              <Input
                readOnly
                value={
                  sslMode === 'tls'
                    ? t('mail.encryption.tlsWithPort')
                    : sslMode === 'ssl'
                      ? t('mail.encryption.sslWithPort')
                      : t('mail.encryption.noneWithPort')
                }
                onClick={() => {
                  const next = sslMode === 'tls' ? 'ssl' : sslMode === 'ssl' ? 'none' : 'tls';
                  setSslMode(next);
                  form.setFieldsValue({
                    ssl_mode: next,
                    mail_port: next === 'ssl' ? 465 : next === 'tls' ? 587 : 25
                  });
                }}
                style={{ cursor: 'pointer' }}
              />
            </Form.Item>

            <Form.Item
              label={t('mail.field.timeout')}
              name="mail_timeout"
              style={{ width: 120, marginBottom: 24 }}
            >
              <InputNumber min={1} max={120} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Divider />

          {/* ─── 认证信息 ──────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            <LockOutlined style={{ marginRight: 8 }} />
            {t('mail.section.auth')}
          </Title>

          <Form.Item
            label={t('mail.field.username')}
            name="mail_username"
            rules={[{ required: true, message: t('mail.validation.usernameRequired') }]}
          >
            <Input placeholder={t('mail.field.usernamePlaceholder')} />
          </Form.Item>

          <Form.Item
            label={
              <Space size={4}>
                <span>{t('mail.field.password')}</span>
                {config?.mail_password_set && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t('mail.field.passwordSetHint')}
                  </Text>
                )}
              </Space>
            }
            name="mail_password"
            rules={
              config?.mail_password_set
                ? []
                : [{ required: true, message: t('mail.validation.passwordRequired') }]
            }
          >
            <Input.Password
              placeholder={
                config?.mail_password_set
                  ? t('mail.field.passwordKeepPlaceholder')
                  : t('mail.field.passwordPlaceholder')
              }
            />
          </Form.Item>

          <Form.Item
            label={t('mail.field.sender')}
            name="mail_default_sender"
            rules={[
              { required: true, message: t('mail.validation.senderRequired') },
              { type: 'email', message: t('mail.validation.emailInvalid') }
            ]}
          >
            <Input placeholder={t('mail.field.usernamePlaceholder')} />
          </Form.Item>

          <Divider />

          {/* ─── 常见服务商快捷配置 ──────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            <SafetyCertificateOutlined style={{ marginRight: 8 }} />
            {t('mail.section.providerPresets')}
          </Title>

          <Space wrap style={{ marginBottom: 24 }}>
            {PROVIDERS.map((provider) => (
              <Button
                key={provider.labelKey}
                size="small"
                onClick={() => {
                  setSslMode(provider.mode);
                  form.setFieldsValue({
                    mail_server: provider.server,
                    mail_port: provider.port,
                    ssl_mode: provider.mode
                  });
                }}
              >
                {t(`mail.provider.${provider.labelKey}`)}
              </Button>
            ))}
          </Space>

          <Divider />

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                {t('saveConfig')}
              </Button>
              <Button onClick={openTestModal} disabled={!form.getFieldValue('mail_server')}>
                {t('mail.action.sendTest')}
              </Button>
              {hasConfig && (
                <Button onClick={handleCancelEdit}>{tCommon('action.cancel')}</Button>
              )}
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default MailConfigPage;
