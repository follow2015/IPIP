/**
 * WebhookConfigPage — Webhook 渠道配置管理页面
 *
 * 仅管理员可见。使用 Ant Design Table + Modal + Form 构建。
 */
import React, { useCallback, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  message,
  Popconfirm,
  Typography,
  Card
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import {
  useWebhookConfigs,
  useCreateWebhookConfig,
  useUpdateWebhookConfig,
  useDeleteWebhookConfig,
  useTestWebhookConfig,
  type WebhookConfig,
  type CreateWebhookConfigParams
} from '@/services/notification';
import {
  NOTIFICATION_TYPE_GROUP_OPTIONS,
  SEVERITY_OPTIONS,
  CHANNEL_LABELS,
  CHANNEL_COLORS,
  BROADCAST_CHANNEL_OPTIONS
} from '@/types/enums';

const { Title, Text } = Typography;

const WebhookConfigPage: React.FC = () => {
  const { data: configs = [], isLoading } = useWebhookConfigs();
  const createMutation = useCreateWebhookConfig();
  const updateMutation = useUpdateWebhookConfig();
  const deleteMutation = useDeleteWebhookConfig();
  const testMutation = useTestWebhookConfig();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<WebhookConfig | null>(null);
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const openCreateModal = useCallback(() => {
    setEditingConfig(null);
    form.resetFields();
    form.setFieldsValue({ channel: 'wechat_work', enabled: true });
    setModalOpen(true);
  }, [form]);

  const openEditModal = useCallback(
    (record: WebhookConfig) => {
      setEditingConfig(record);
      form.setFieldsValue({
        name: record.name,
        channel: record.channel,
        url: record.url,
        secret: record.secret,
        enabled: record.enabled,
        applicable_types: record.applicable_types,
        applicable_severities: record.applicable_severities
      });
      setModalOpen(true);
    },
    [form]
  );

  const handleSubmit = useCallback(
    async (values: CreateWebhookConfigParams) => {
      try {
        if (editingConfig) {
          await updateMutation.mutateAsync({ id: editingConfig.id, data: values });
          messageApi.success('更新成功');
        } else {
          await createMutation.mutateAsync(values);
          messageApi.success('创建成功');
        }
        setModalOpen(false);
      } catch {
        messageApi.error('操作失败');
      }
    },
    [editingConfig, createMutation, updateMutation, messageApi]
  );

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteMutation.mutateAsync(id);
        messageApi.success('删除成功');
      } catch {
        messageApi.error('删除失败');
      }
    },
    [deleteMutation, messageApi]
  );

  const handleTest = useCallback(
    async (id: number) => {
      try {
        const result = await testMutation.mutateAsync(id);
        if (result.success) {
          messageApi.success(result.message);
        } else {
          messageApi.error(result.message);
        }
      } catch {
        messageApi.error('测试请求失败');
      }
    },
    [testMutation, messageApi]
  );

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160
    },
    {
      title: '渠道',
      dataIndex: 'channel',
      key: 'channel',
      width: 100,
      render: (ch: string) => (
        <Tag color={CHANNEL_COLORS[ch] ?? 'default'}>{CHANNEL_LABELS[ch] ?? ch}</Tag>
      )
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      width: 280,
      ellipsis: true
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean) =>
        enabled ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            启用
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="default">
            禁用
          </Tag>
        )
    },
    {
      title: '适用严重程度',
      dataIndex: 'applicable_severities',
      key: 'applicable_severities',
      width: 180,
      render: (severities: string[] | null) =>
        severities?.length ? (
          severities.map((s) => <Tag key={s}>{s}</Tag>)
        ) : (
          <Text type="secondary">全部</Text>
        )
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: WebhookConfig) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            loading={testMutation.isPending}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除此配置？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <>
      {contextHolder}
      <Card>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16
          }}
        >
          <Title level={5} style={{ margin: 0 }}>
            Webhook 渠道配置
          </Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新增配置
          </Button>
        </div>

        <Table
          dataSource={configs}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={false}
          size="middle"
        />
      </Card>

      <Modal
        title={editingConfig ? '编辑 Webhook 配置' : '新增 Webhook 配置'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="配置名称"
            name="name"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="如：运维群机器人" />
          </Form.Item>

          <Form.Item
            label="渠道类型"
            name="channel"
            rules={[{ required: true, message: '请选择渠道类型' }]}
          >
            <Select options={BROADCAST_CHANNEL_OPTIONS} />
          </Form.Item>

          <Form.Item
            label="Webhook URL"
            name="url"
            rules={[
              { required: true, message: '请输入 Webhook URL' },
              { type: 'url', message: '请输入有效的 URL' }
            ]}
          >
            <Input placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=***" />
          </Form.Item>

          <Form.Item label="签名密钥（可选）" name="secret">
            <Input.Password placeholder="飞书群机器人签名密钥" />
          </Form.Item>

          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch defaultChecked />
          </Form.Item>

          <Form.Item label="适用通知类型（空=全部）" name="applicable_types">
            <Select
              mode="multiple"
              placeholder="选择通知类型"
              options={NOTIFICATION_TYPE_GROUP_OPTIONS}
              allowClear
            />
          </Form.Item>

          <Form.Item label="适用严重程度（空=全部）" name="applicable_severities">
            <Select mode="multiple" options={SEVERITY_OPTIONS} placeholder="选择严重程度" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default WebhookConfigPage;
