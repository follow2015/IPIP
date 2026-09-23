/**
 * G4.2: 升级策略管理页
 *
 * 告警在 N 分钟未确认时升级：
 * - 提升严重级别（warning → critical）
 * - 通知更高级别用户组（escalate_to_role_id）
 * - 可选触发外部 webhook
 *
 * P2-11: 支持多级升级链（steps 数组），按 step_no 顺序渐进升级。
 *       无 steps 时回退单级模式（wait_minutes + repeat_minutes）。
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
  Divider,
  Empty
} from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, MinusOutlined } from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import {
  useEscalationPolicies,
  useCreateEscalationPolicy,
  useUpdateEscalationPolicy,
  useDeleteEscalationPolicy,
  type MonitorEscalationPolicy,
  type MonitorEscalationPolicyInput,
  type MonitorEscalationStepInput
} from '@/services/monitor';
import { formatDateTime } from '@/utils/format';
import { getSeverityOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

const ALERT_TYPE_OPTIONS = [
  { label: 'device_unreachable', value: 'device_unreachable' },
  { label: 'temperature_alert', value: 'temperature_alert' },
  { label: 'disk_failure', value: 'disk_failure' },
  { label: 'raid_failure', value: 'raid_failure' },
  { label: 'monitor_interrupted', value: 'monitor_interrupted' }
];

export default function EscalationPoliciesPage() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const { data, isLoading } = useEscalationPolicies();
  const createMut = useCreateEscalationPolicy();
  const updateMut = useUpdateEscalationPolicy();
  const deleteMut = useDeleteEscalationPolicy();
  const modal = useDisclosure();
  const [editing, setEditing] = useState<MonitorEscalationPolicy | null>(null);
  const [form] = Form.useForm<MonitorEscalationPolicyInput>();
  const table = useTable({ initialPerPage: 20 });
  const message = useMessage();

  const items: MonitorEscalationPolicy[] = data?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, wait_minutes: 30, repeat_minutes: 0, steps: [] });
    modal.open();
  };

  const openEdit = (record: MonitorEscalationPolicy) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      alert_type: record.alert_type ?? undefined,
      severity: record.severity ?? undefined,
      wait_minutes: record.wait_minutes,
      escalate_severity: record.escalate_severity ?? undefined,
      escalate_to_role_id: record.escalate_to_role_id ?? undefined,
      escalate_webhook_url: record.escalate_webhook_url ?? undefined,
      repeat_minutes: record.repeat_minutes,
      enabled: record.enabled,
      steps: (record.steps ?? []).map((s) => ({
        step_no: s.step_no,
        wait_minutes: s.wait_minutes,
        escalate_severity: s.escalate_severity ?? null,
        escalate_to_role_id: s.escalate_to_role_id ?? null,
        escalate_webhook_url: s.escalate_webhook_url ?? null,
        enabled: s.enabled
      }))
    });
    modal.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: MonitorEscalationPolicyInput = {
        name: values.name,
        alert_type: values.alert_type ?? null,
        severity: values.severity ?? null,
        wait_minutes: values.wait_minutes,
        escalate_severity: values.escalate_severity ?? null,
        escalate_to_role_id: values.escalate_to_role_id ?? null,
        escalate_webhook_url: values.escalate_webhook_url ?? null,
        repeat_minutes: values.repeat_minutes ?? 0,
        enabled: values.enabled ?? true,
        steps: (values.steps ?? []).map((s: MonitorEscalationStepInput, idx: number) => ({
          step_no: s.step_no ?? idx + 1,
          wait_minutes: s.wait_minutes,
          escalate_severity: s.escalate_severity ?? null,
          escalate_to_role_id: s.escalate_to_role_id ?? null,
          escalate_webhook_url: s.escalate_webhook_url ?? null,
          enabled: s.enabled ?? true
        }))
      };
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, ...payload });
        message.success(t('escalation.message.updated'));
      } else {
        await createMut.mutateAsync(payload);
        message.success(t('escalation.message.created'));
      }
      modal.close();
    } catch (err: unknown) {
      if (err instanceof Error && err.message) message.error(err.message);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success(t('escalation.message.deleted'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const columns = [
    {
      title: tc('field.name'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r: MonitorEscalationPolicy) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">{t('metricTemplate.status.disabled')}</Tag>}
        </Space>
      )
    },
    {
      title: t('escalation.column.match'),
      key: 'match',
      render: (_: unknown, r: MonitorEscalationPolicy) => (
        <Space size={4}>
          {r.alert_type ? (
            <Tag color="blue">{r.alert_type}</Tag>
          ) : (
            <Tag>{t('escalation.matchAllTypes')}</Tag>
          )}
          {r.severity ? (
            <Tag color="orange">{r.severity}</Tag>
          ) : (
            <Tag>{t('escalation.matchAllSeverities')}</Tag>
          )}
        </Space>
      )
    },
    {
      title: t('escalation.column.mode'),
      key: 'mode',
      render: (_: unknown, r: MonitorEscalationPolicy) => {
        const steps = r.steps ?? [];
        if (steps.length > 0) {
          return (
            <Space size={4} wrap>
              <Tag color="gold">{t('escalation.mode.multiStep', { count: steps.length })}</Tag>
              {steps.map((s) => (
                <Tag key={s.id} color={s.enabled ? 'blue' : 'default'}>
                  {s.step_no}:{s.wait_minutes}min
                  {s.escalate_severity ? `→${s.escalate_severity}` : ''}
                </Tag>
              ))}
            </Space>
          );
        }
        return (
          <Space size={4} wrap>
            <Tag>{t('escalation.mode.singleStep', { minutes: r.wait_minutes })}</Tag>
            {r.escalate_severity && <Tag color="red">→{r.escalate_severity}</Tag>}
            {r.escalate_to_role_id && (
              <Tag color="purple">{t('escalation.mode.role', { id: r.escalate_to_role_id })}</Tag>
            )}
            {r.escalate_webhook_url && <Tag color="cyan">webhook</Tag>}
            {r.repeat_minutes > 0 && (
              <Tag>{t('escalation.mode.repeat', { minutes: r.repeat_minutes })}</Tag>
            )}
          </Space>
        );
      }
    },
    {
      title: tc('field.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => <Text type="secondary">{formatDateTime(v)}</Text>
    },
    {
      title: tc('field.actions'),
      key: 'op',
      render: (_: unknown, r: MonitorEscalationPolicy) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            {tc('action.edit')}
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={t('escalation.confirm.deleteContent')}
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
      <Card
        title={t('escalation.title')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('escalation.action.create')}
          </Button>
        }
      >
        <DataTable<MonitorEscalationPolicy>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText={t('escalation.empty')}
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? t('escalation.modal.editTitle') : t('escalation.modal.createTitle')}
        open={modal.isOpen}
        onOk={handleSubmit}
        onCancel={() => modal.close()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label={t('escalation.field.name')}
            rules={[{ required: true, message: t('escalation.validation.nameRequired') }]}
          >
            <Input placeholder={t('escalation.placeholder.name')} maxLength={128} />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="alert_type" label={t('escalation.field.alertType')} style={{ flex: 1 }}>
              <Select
                placeholder={t('escalation.matchAllTypes')}
                options={ALERT_TYPE_OPTIONS}
                allowClear
              />
            </Form.Item>
            <Form.Item name="severity" label={t('escalation.field.severity')} style={{ flex: 1 }}>
              <Select
                placeholder={t('escalation.matchAllSeverities')}
                options={getSeverityOptions(td)}
                allowClear
              />
            </Form.Item>
          </Space>

          <Divider titlePlacement="left" plain>
            {t('escalation.section.multiStepTitle')}
          </Divider>
          <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
            {t('escalation.section.multiStepHint')}
          </Text>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, idx) => (
                  <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="start">
                    <Tag color="gold">{t('escalation.step.label', { index: idx + 1 })}</Tag>
                    <Form.Item
                      {...field}
                      name={[field.name, 'wait_minutes']}
                      rules={[{ required: true, message: tc('validation.required') }]}
                      style={{ marginBottom: 0 }}
                    >
                      <InputNumber
                        min={1}
                        placeholder={t('escalation.step.waitMinutesPlaceholder')}
                        style={{ width: 110 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_severity']}
                      style={{ marginBottom: 0 }}
                    >
                      <Select
                        placeholder={t('escalation.step.escalateSeverityPlaceholder')}
                        options={getSeverityOptions(td)}
                        allowClear
                        style={{ width: 120 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_to_role_id']}
                      style={{ marginBottom: 0 }}
                    >
                      <InputNumber
                        min={1}
                        placeholder={t('escalation.step.roleIdPlaceholder')}
                        style={{ width: 100 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_webhook_url']}
                      style={{ marginBottom: 0, flex: 1 }}
                    >
                      <Input
                        placeholder={t('escalation.step.webhookPlaceholder')}
                        maxLength={512}
                        style={{ width: 200 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'enabled']}
                      valuePropName="checked"
                      style={{ marginBottom: 0 }}
                    >
                      <Switch />
                    </Form.Item>
                    <Button
                      type="link"
                      danger
                      icon={<MinusOutlined />}
                      onClick={() => remove(field.name)}
                    />
                  </Space>
                ))}
                {fields.length === 0 && (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('escalation.step.empty')}
                    style={{ margin: '8px 0' }}
                  />
                )}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => add({ wait_minutes: 30, enabled: true })}
                  block
                >
                  {t('escalation.step.add')}
                </Button>
              </>
            )}
          </Form.List>

          <Divider titlePlacement="left" plain>
            {t('escalation.section.singleStepTitle')}
          </Divider>
          <Form.Item
            name="wait_minutes"
            label={t('escalation.field.waitMinutes')}
            rules={[{ required: true, message: t('escalation.validation.waitMinutesRequired') }]}
          >
            <InputNumber
              min={1}
              style={{ width: '100%' }}
              placeholder={t('escalation.placeholder.waitMinutes')}
            />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="escalate_severity" label={t('escalation.field.escalateSeverity')} style={{ flex: 1 }}>
              <Select
                placeholder={t('escalation.placeholder.escalateSeverity')}
                options={getSeverityOptions(td)}
                allowClear
              />
            </Form.Item>
            <Form.Item name="escalate_to_role_id" label={t('escalation.field.escalateToRoleId')} style={{ flex: 1 }}>
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder={t('escalation.placeholder.roleId')}
              />
            </Form.Item>
          </Space>
          <Form.Item name="escalate_webhook_url" label={t('escalation.field.webhookUrl')}>
            <Input placeholder="https://example.com/hook" maxLength={512} />
          </Form.Item>
          <Form.Item
            name="repeat_minutes"
            label={t('escalation.field.repeatMinutes')}
            extra={t('escalation.field.repeatMinutesExtra')}
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
