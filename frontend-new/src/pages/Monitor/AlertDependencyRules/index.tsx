/**
 * P2-17: 告警依赖抑制规则管理页
 *
 * 当上游设备有 active 告警时，抑制下游设备的同类型告警，
 * 避免网络抖动时下游设备大量告警淹没根因。
 *
 * 自动推断：DeviceServerExt.parent_device_id 拓扑关系自动生效（无需在此配置）
 * 手动规则：在此页显式配置上游→下游的依赖关系，可覆盖/补充自动推断
 */
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  InputNumber,
  Switch,
  Select,
  Typography,
  Alert
} from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import {
  useAlertDependencyRules,
  useCreateAlertDependencyRule,
  useUpdateAlertDependencyRule,
  useDeleteAlertDependencyRule,
  type MonitorAlertDependencyRule,
  type MonitorAlertDependencyRuleInput
} from '@/services/monitor';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

const ALERT_TYPE_OPTIONS = [
  { label: 'device_unreachable', value: 'device_unreachable' },
  { label: 'device_recovered', value: 'device_recovered' },
  { label: 'temperature_alert', value: 'temperature_alert' },
  { label: 'disk_failure', value: 'disk_failure' },
  { label: 'port_status_changed', value: 'port_status_changed' },
  { label: 'monitor_interrupted', value: 'monitor_interrupted' },
  { label: 'raid_failure', value: 'raid_failure' }
];

export default function AlertDependencyRulesPage() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { data, isLoading } = useAlertDependencyRules();
  const createMut = useCreateAlertDependencyRule();
  const updateMut = useUpdateAlertDependencyRule();
  const deleteMut = useDeleteAlertDependencyRule();
  const modal = useDisclosure();
  const [editing, setEditing] = useState<MonitorAlertDependencyRule | null>(null);
  const message = useMessage();
  const [form] = Form.useForm<{
    name: string;
    upstream_device_id: number;
    downstream_device_id: number;
    alert_types?: string[];
    reason?: string;
    enabled?: boolean;
  }>();
  const table = useTable({ initialPerPage: 20 });

  const items: MonitorAlertDependencyRule[] = data?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true });
    modal.open();
  };

  const openEdit = (record: MonitorAlertDependencyRule) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      upstream_device_id: record.upstream_device_id,
      downstream_device_id: record.downstream_device_id,
      alert_types: record.alert_types ?? undefined,
      reason: record.reason ?? undefined,
      enabled: record.enabled
    });
    modal.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (values.upstream_device_id === values.downstream_device_id) {
        message.error(t('dependency.validation.sameDevice'));
        return;
      }
      const payload: MonitorAlertDependencyRuleInput = {
        name: values.name,
        upstream_device_id: values.upstream_device_id,
        downstream_device_id: values.downstream_device_id,
        alert_types: values.alert_types ?? null,
        reason: values.reason,
        enabled: values.enabled ?? true
      };
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, ...payload });
        message.success(t('crud.updated'));
      } else {
        await createMut.mutateAsync(payload);
        message.success(t('crud.created'));
      }
      modal.close();
    } catch (err: unknown) {
      if (err instanceof Error && err.message) message.error(err.message);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success(t('crud.deleted'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('crud.deleteFailed'));
    }
  };

  const columns = [
    {
      title: tc('field.name'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r: MonitorAlertDependencyRule) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">{t('credential.status.disabled')}</Tag>}
        </Space>
      )
    },
    {
      title: t('dependency.column.upstreamDeviceId'),
      dataIndex: 'upstream_device_id',
      key: 'upstream_device_id',
      render: (v: number) => <Tag color="red">{v}</Tag>
    },
    {
      title: t('dependency.column.downstreamDeviceId'),
      dataIndex: 'downstream_device_id',
      key: 'downstream_device_id',
      render: (v: number) => <Tag color="orange">{v}</Tag>
    },
    {
      title: t('column.alertType'),
      dataIndex: 'alert_types',
      key: 'alert_types',
      render: (v: string[] | null) =>
        v === null || v.length === 0 ? (
          <Tag color="blue">{t('escalation.matchAllTypes')}</Tag>
        ) : (
          v.map((t) => <Tag key={t}>{t}</Tag>)
        )
    },
    {
      title: t('dependency.column.reason'),
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: MonitorAlertDependencyRule) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            {tc('action.edit')}
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={t('dependency.confirm.deleteContent')}
            onConfirm={() => handleDelete(r.id)}
          >
            {tc('action.delete')}
          </ConfirmButton>
        </Space>
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert
        type="info"
        showIcon
        message={t('dependency.alert.title')}
        description={t('dependency.alert.description')}
      />
      <Card
        title={t('dependency.title')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('dependency.action.create')}
          </Button>
        }
      >
        <DataTable<MonitorAlertDependencyRule>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText={t('dependency.empty')}
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? t('dependency.modal.editTitle') : t('dependency.modal.createTitle')}
        open={modal.isOpen}
        onOk={handleSubmit}
        onCancel={() => modal.close()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label={t('dependency.field.name')}
            rules={[
              { required: true, message: tc('validation.inputRequiredField', { field: tc('field.name') }) }
            ]}
          >
            <Input placeholder={t('dependency.placeholder.name')} maxLength={128} />
          </Form.Item>
          <Form.Item
            name="upstream_device_id"
            label={t('dependency.column.upstreamDeviceId')}
            rules={[{ required: true, message: t('dependency.validation.upstreamRequired') }]}
          >
            <InputNumber placeholder={t('dependency.placeholder.upstreamId')} style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item
            name="downstream_device_id"
            label={t('dependency.column.downstreamDeviceId')}
            rules={[{ required: true, message: t('dependency.validation.downstreamRequired') }]}
          >
            <InputNumber placeholder={t('dependency.placeholder.downstreamId')} style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="alert_types" label={t('dependency.field.alertTypes')}>
            <Select
              mode="multiple"
              placeholder={t('placeholder.alertTypesOptional')}
              options={ALERT_TYPE_OPTIONS}
              allowClear
            />
          </Form.Item>
          <Form.Item name="reason" label={t('dependency.field.reason')}>
            <Input.TextArea
              rows={2}
              placeholder={t('dependency.placeholder.reason')}
              maxLength={255}
            />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
