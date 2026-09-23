/**
 * WebhookConfigPage — Webhook 渠道配置管理页面
 *
 * 仅管理员可见。使用 Ant Design Table + Modal + Form 构建。
 */
import React, { useCallback, useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  message,
  Typography,
  Card
} from 'antd';
import DataTable from '@/components/DataTable';
import { useConfirm } from '@/utils/confirm';
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
import { CHANNEL_COLORS } from '@/types/enums';
import {
  getBroadcastChannelOptions,
  getChannelLabel,
  getNotificationTypeGroupOptions,
  getSeverityOptions
} from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

const WebhookConfigPage: React.FC = () => {
  const { t: tDevice } = useTranslation('device');
  const { t } = useTranslation('settings');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const { data: configs = [], isLoading } = useWebhookConfigs();
  const createMutation = useCreateWebhookConfig();
  const updateMutation = useUpdateWebhookConfig();
  const deleteMutation = useDeleteWebhookConfig();
  const testMutation = useTestWebhookConfig();

  const modal = useDisclosure();
  const [editingConfig, setEditingConfig] = useState<WebhookConfig | null>(null);
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const openCreateModal = useCallback(() => {
    setEditingConfig(null);
    form.resetFields();
    form.setFieldsValue({ channel: 'wechat_work', enabled: true });
    modal.open();
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
      modal.open();
    },
    [form]
  );

  const handleSubmit = useCallback(
    async (values: CreateWebhookConfigParams) => {
      try {
        if (editingConfig) {
          await updateMutation.mutateAsync({ id: editingConfig.id, data: values });
          messageApi.success(tCommon('message.updateSuccess'));
        } else {
          await createMutation.mutateAsync(values);
          messageApi.success(tCommon('message.createSuccess'));
        }
        modal.close();
      } catch {
        messageApi.error(tCommon('message.operationFailed'));
      }
    },
    [editingConfig, createMutation, updateMutation, messageApi, tCommon]
  );

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteMutation.mutateAsync(id);
        messageApi.success(tCommon('message.deleteSuccess'));
      } catch {
        messageApi.error(tCommon('message.deleteFailed'));
      }
    },
    [deleteMutation, messageApi, tCommon]
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
        messageApi.error(t('testRequestFailed'));
      }
    },
    [testMutation, messageApi, t]
  );

  const columns = [
    {
      title: tCommon('field.name'),
      dataIndex: 'name',
      key: 'name',
      width: 160
    },
    {
      title: t('webhook.column.channel'),
      dataIndex: 'channel',
      key: 'channel',
      width: 100,
      render: (ch: string) => (
        <Tag color={CHANNEL_COLORS[ch] ?? 'default'}>{getChannelLabel(ch, tDevice) ?? ch}</Tag>
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
      title: tCommon('field.status'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean) =>
        enabled ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            {tCommon('action.enable')}
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="default">
            {tCommon('action.disable')}
          </Tag>
        )
    },
    {
      title: t('webhook.column.severity'),
      dataIndex: 'applicable_severities',
      key: 'applicable_severities',
      width: 180,
      render: (severities: string[] | null) =>
        severities?.length ? (
          severities.map((s) => <Tag key={s}>{s}</Tag>)
        ) : (
          <Text type="secondary">{t('webhook.column.severityAll')}</Text>
        )
    },
    {
      title: tCommon('field.actions'),
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
            {t('webhook.action.test')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            {tCommon('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              confirm({
                title: t('webhook.action.deleteConfirmTitle'),
                okText: tCommon('action.delete'),
                cancelText: tCommon('action.cancel'),
                okButtonProps: { danger: true },
                onOk: () => handleDelete(record.id)
              })
            }
          >
            {tCommon('action.delete')}
          </Button>
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
            {t('webhook.title')}
          </Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            {t('webhook.action.create')}
          </Button>
        </div>

        <DataTable
          dataSource={configs}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
          showCard={false}
          searchable={false}
        />
      </Card>

      <Modal
        title={
          editingConfig ? t('webhook.modalTitle.edit') : t('webhook.modalTitle.create')
        }
        open={modal.isOpen}
        onCancel={() => modal.close()}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label={t('webhook.field.name')}
            name="name"
            rules={[{ required: true, message: t('webhook.validation.nameRequired') }]}
          >
            <Input placeholder={t('webhook.field.namePlaceholder')} />
          </Form.Item>

          <Form.Item
            label={t('webhook.field.channel')}
            name="channel"
            rules={[{ required: true, message: t('webhook.validation.channelRequired') }]}
          >
            <Select options={getBroadcastChannelOptions(tDevice)} />
          </Form.Item>

          <Form.Item
            label={t('webhook.field.url')}
            name="url"
            rules={[
              { required: true, message: t('webhook.validation.urlRequired') },
              { type: 'url', message: t('webhook.validation.urlInvalid') }
            ]}
          >
            <Input placeholder={t('webhook.field.urlPlaceholder')} />
          </Form.Item>

          <Form.Item label={t('webhook.field.secret')} name="secret">
            <Input.Password placeholder={t('webhook.field.secretPlaceholder')} />
          </Form.Item>

          <Form.Item
            label={tCommon('action.enable')}
            name="enabled"
            valuePropName="checked"
          >
            <Switch defaultChecked />
          </Form.Item>

          <Form.Item label={t('webhook.field.types')} name="applicable_types">
            <Select
              mode="multiple"
              placeholder={t('webhook.field.typesPlaceholder')}
              options={getNotificationTypeGroupOptions(tDevice)}
              allowClear
            />
          </Form.Item>

          <Form.Item label={t('webhook.field.severities')} name="applicable_severities">
            <Select
              mode="multiple"
              options={getSeverityOptions(tDevice)}
              placeholder={t('webhook.field.severitiesPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default WebhookConfigPage;
