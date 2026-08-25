/**
 * MailConfigPage — 邮件服务器配置管理页面
 *
 * 仅管理员可见。支持查看已保存配置、编辑、删除（重置）、连通性测试。
 * 三种视图状态：未配置 → 配置表单；已配置 → 查看卡片 → 编辑表单。
 * 测试邮件时弹出 Modal 填写收件人地址。
 */
import React, { useCallback, useState } from 'react';
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
  Popconfirm,
  Descriptions,
  Tag,
  Modal,
} from 'antd';
import {
  MailOutlined,
  SendOutlined,
  QuestionCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import {
  useMailConfig,
  useUpdateMailConfig,
  useDeleteMailConfig,
  useTestMailConfig,
  type MailConfig,
  type MailConfigUpdate,
} from '@/services/mail-settings';

const { Title, Text } = Typography;


const SSL_MODE_MAP = {
  tls: { label: 'STARTTLS', color: 'blue' },
  ssl: { label: 'SSL', color: 'green' },
  none: { label: '无加密', color: 'default' },
} as const;


const PROVIDERS = [
  { label: '腾讯企业邮', server: 'smtp.exmail.qq.com', port: 465, mode: 'ssl' as const },
  { label: '阿里企业邮', server: 'smtp.qiye.aliyun.com', port: 465, mode: 'ssl' as const },
  { label: 'QQ 邮箱', server: 'smtp.qq.com', port: 465, mode: 'ssl' as const },
  { label: '163 邮箱', server: 'smtp.163.com', port: 465, mode: 'ssl' as const },
  { label: 'Gmail', server: 'smtp.gmail.com', port: 587, mode: 'tls' as const },
  { label: 'SendGrid', server: 'smtp.sendgrid.net', port: 587, mode: 'tls' as const },
];

const MailConfigPage: React.FC = () => {
  const { data: config, isLoading } = useMailConfig();
  const updateMutation = useUpdateMailConfig();
  const deleteMutation = useDeleteMailConfig();
  const testMutation = useTestMailConfig();
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [sslMode, setSslMode] = useState<'tls' | 'ssl' | 'none'>('tls');
  const [editing, setEditing] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);

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
        mail_timeout: cfg.mail_timeout,
      });
    },
    [form],
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
        mail_timeout: values.mail_timeout,
      };
      try {
        await updateMutation.mutateAsync(update);
        messageApi.success('邮件配置已保存');
        setEditing(false);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : '保存失败，请重试';
        messageApi.error(msg);
      }
    },
    [updateMutation, messageApi],
  );

  const handleDelete = useCallback(async () => {
    try {
      await deleteMutation.mutateAsync();
      messageApi.success('邮件配置已删除');
      setEditing(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除失败，请重试';
      messageApi.error(msg);
    }
  }, [deleteMutation, messageApi]);

  
  const openTestModal = useCallback(() => {
    testForm.resetFields();
    setTestModalOpen(true);
  }, [testForm]);

  
  const handleTestSend = useCallback(async () => {
    try {
      const values = await testForm.validateFields();
      const result = await testMutation.mutateAsync({ recipient: values.recipient });
      if (result.success) {
        messageApi.success(result.message);
        setTestModalOpen(false);
      } else {
        messageApi.error(result.message);
      }
    } catch (err: unknown) {
      
      if (err && typeof err === 'object' && 'message' in err) {
        messageApi.error((err as { message: string }).message || '测试请求失败');
      }
    }
  }, [testMutation, testForm, messageApi]);

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
      title="发送测试邮件"
      open={testModalOpen}
      onOk={handleTestSend}
      onCancel={() => setTestModalOpen(false)}
      okText="发送"
      cancelText="取消"
      confirmLoading={testMutation.isPending}
      destroyOnClose
    >
      <Form form={testForm} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="recipient"
          label="收件人邮箱"
          rules={[
            { required: true, message: '请输入收件人邮箱地址' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input placeholder="请输入收件人邮箱地址" prefix={<MailOutlined />} />
        </Form.Item>
      </Form>
      <Alert
        type="info"
        showIcon
        message="将使用当前已保存的 SMTP 配置发送测试邮件到上方地址。"
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Space>
              <MailOutlined style={{ fontSize: 18 }} />
              <Title level={5} style={{ margin: 0 }}>邮件服务器配置</Title>
              <Tag color="green" icon={<CheckCircleOutlined />}>已配置</Tag>
            </Space>
            <Space>
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={openTestModal}
              >
                发送测试邮件
              </Button>
              <Button icon={<EditOutlined />} onClick={handleEdit}>
                编辑
              </Button>
              <Popconfirm
                title="确认删除邮件配置？"
                description="删除后邮件通知将不可用，需要重新配置。"
                onConfirm={handleDelete}
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button danger icon={<DeleteOutlined />} loading={deleteMutation.isPending}>
                  删除
                </Button>
              </Popconfirm>
            </Space>
          </div>

          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
            message="配置保存后即时生效，无需重启服务。"
          />

          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="SMTP 服务器">{config.mail_server}</Descriptions.Item>
            <Descriptions.Item label="端口">{config.mail_port}</Descriptions.Item>
            <Descriptions.Item label="加密方式">
              <Tag color={modeInfo.color}>{modeInfo.label}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="超时">{config.mail_timeout} 秒</Descriptions.Item>
            <Descriptions.Item label="用户名">{config.mail_username}</Descriptions.Item>
            <Descriptions.Item label="密码">
              {config.mail_password_set ? (
                <Text type="secondary">••••••••</Text>
              ) : (
                <Tag color="warning" icon={<CloseCircleOutlined />}>未设置</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="发件人地址" span={2}>{config.mail_default_sender}</Descriptions.Item>
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Space>
            <MailOutlined style={{ fontSize: 18 }} />
            <Title level={5} style={{ margin: 0 }}>
              {hasConfig ? '编辑邮件服务器配置' : '配置邮件服务器'}
            </Title>
            {hasConfig && <Tag color="blue">编辑中</Tag>}
          </Space>
          <Space>
            {hasConfig && (
              <Button onClick={handleCancelEdit}>取消</Button>
            )}
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
          message="配置保存后即时生效，无需重启服务。"
        />

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
        >
          {}
          <Title level={5} style={{ marginBottom: 16 }}>服务器连接</Title>

          <Form.Item
            label="SMTP 服务器地址"
            name="mail_server"
            rules={[{ required: true, message: '请输入 SMTP 服务器地址' }]}
          >
            <Input placeholder="如：smtp.exmail.qq.com" />
          </Form.Item>

          <Space size={16} style={{ width: '100%' }} align="start">
            <Form.Item
              label="端口"
              name="mail_port"
              rules={[{ required: true, message: '请输入端口号' }]}
              style={{ width: 120, marginBottom: 24 }}
            >
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              label={
                <Space size={4}>
                  <span>加密方式</span>
                  <Tooltip title="STARTTLS：端口 587，先明文连接再升级加密（Gmail/SendGrid）；SSL：端口 465，全程加密（腾讯企业邮/阿里企业邮）">
                    <QuestionCircleOutlined style={{ color: '#999' }} />
                  </Tooltip>
                </Space>
              }
              name="ssl_mode"
              rules={[{ required: true, message: '请选择加密方式' }]}
              style={{ width: 200, marginBottom: 24 }}
            >
              <Input
                readOnly
                value={sslMode === 'tls' ? 'STARTTLS (587)' : sslMode === 'ssl' ? 'SSL (465)' : '无加密 (25)'}
                onClick={() => {
                  const next = sslMode === 'tls' ? 'ssl' : sslMode === 'ssl' ? 'none' : 'tls';
                  setSslMode(next);
                  form.setFieldsValue({
                    ssl_mode: next,
                    mail_port: next === 'ssl' ? 465 : next === 'tls' ? 587 : 25,
                  });
                }}
                style={{ cursor: 'pointer' }}
              />
            </Form.Item>

            <Form.Item
              label="超时（秒）"
              name="mail_timeout"
              style={{ width: 120, marginBottom: 24 }}
            >
              <InputNumber min={1} max={120} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Divider />

          {}
          <Title level={5} style={{ marginBottom: 16 }}>
            <LockOutlined style={{ marginRight: 8 }} />
            认证信息
          </Title>

          <Form.Item
            label="用户名"
            name="mail_username"
            rules={[{ required: true, message: '请输入 SMTP 认证用户名' }]}
          >
            <Input placeholder="如：alert@yourcompany.com" />
          </Form.Item>

          <Form.Item
            label={
              <Space size={4}>
                <span>密码/授权码</span>
                {config?.mail_password_set && (
                  <Text type="secondary" style={{ fontSize: 12 }}>(已设置，留空则保持原值)</Text>
                )}
              </Space>
            }
            name="mail_password"
            rules={config?.mail_password_set ? [] : [{ required: true, message: '请输入 SMTP 认证密码' }]}
          >
            <Input.Password placeholder={config?.mail_password_set ? '留空保持原密码' : 'SMTP 认证密码或授权码'} />
          </Form.Item>

          <Form.Item
            label="发件人地址"
            name="mail_default_sender"
            rules={[
              { required: true, message: '请输入发件人地址' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input placeholder="如：alert@yourcompany.com" />
          </Form.Item>

          <Divider />

          {}
          <Title level={5} style={{ marginBottom: 16 }}>
            <SafetyCertificateOutlined style={{ marginRight: 8 }} />
            常见服务商快捷配置
          </Title>

          <Space wrap style={{ marginBottom: 24 }}>
            {PROVIDERS.map((provider) => (
              <Button
                key={provider.label}
                size="small"
                onClick={() => {
                  setSslMode(provider.mode);
                  form.setFieldsValue({
                    mail_server: provider.server,
                    mail_port: provider.port,
                    ssl_mode: provider.mode,
                  });
                }}
              >
                {provider.label}
              </Button>
            ))}
          </Space>

          <Divider />

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                保存配置
              </Button>
              <Button onClick={openTestModal} disabled={!form.getFieldValue('mail_server')}>
                发送测试邮件
              </Button>
              {hasConfig && (
                <Button onClick={handleCancelEdit}>取消</Button>
              )}
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default MailConfigPage;
