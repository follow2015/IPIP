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

const { Text } = Typography;

const SEVERITY_OPTIONS = [
  { label: 'info', value: 'info' },
  { label: 'warning', value: 'warning' },
  { label: 'critical', value: 'critical' }
];

const ALERT_TYPE_OPTIONS = [
  { label: 'device_unreachable', value: 'device_unreachable' },
  { label: 'temperature_alert', value: 'temperature_alert' },
  { label: 'disk_failure', value: 'disk_failure' },
  { label: 'raid_failure', value: 'raid_failure' },
  { label: 'monitor_interrupted', value: 'monitor_interrupted' }
];

export default function EscalationPoliciesPage() {
  const { data, isLoading } = useEscalationPolicies();
  const createMut = useCreateEscalationPolicy();
  const updateMut = useUpdateEscalationPolicy();
  const deleteMut = useDeleteEscalationPolicy();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MonitorEscalationPolicy | null>(null);
  const [form] = Form.useForm<MonitorEscalationPolicyInput>();
  const table = useTable({ initialPerPage: 20 });
  const message = useMessage();

  const items: MonitorEscalationPolicy[] = data?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, wait_minutes: 30, repeat_minutes: 0, steps: [] });
    setModalOpen(true);
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
    setModalOpen(true);
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
        message.success('已更新');
      } else {
        await createMut.mutateAsync(payload);
        message.success('已创建');
      }
      setModalOpen(false);
    } catch (err: unknown) {
      if (err instanceof Error && err.message) message.error(err.message);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success('已删除');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r: MonitorEscalationPolicy) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">已停用</Tag>}
        </Space>
      )
    },
    {
      title: '匹配条件',
      key: 'match',
      render: (_: unknown, r: MonitorEscalationPolicy) => (
        <Space size={4}>
          {r.alert_type ? <Tag color="blue">{r.alert_type}</Tag> : <Tag>全部类型</Tag>}
          {r.severity ? <Tag color="orange">{r.severity}</Tag> : <Tag>全部级别</Tag>}
        </Space>
      )
    },
    {
      title: '升级模式',
      key: 'mode',
      render: (_: unknown, r: MonitorEscalationPolicy) => {
        const steps = r.steps ?? [];
        if (steps.length > 0) {
          return (
            <Space size={4} wrap>
              <Tag color="gold">多级链({steps.length}步)</Tag>
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
            <Tag>单级 {r.wait_minutes}min</Tag>
            {r.escalate_severity && <Tag color="red">→{r.escalate_severity}</Tag>}
            {r.escalate_to_role_id && <Tag color="purple">角色#{r.escalate_to_role_id}</Tag>}
            {r.escalate_webhook_url && <Tag color="cyan">webhook</Tag>}
            {r.repeat_minutes > 0 && <Tag>每{r.repeat_minutes}min重复</Tag>}
          </Space>
        );
      }
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => <Text type="secondary">{formatDateTime(v)}</Text>
    },
    {
      title: '操作',
      key: 'op',
      render: (_: unknown, r: MonitorEscalationPolicy) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该升级策略吗？此操作不可恢复。"
            onConfirm={() => handleDelete(r.id)}
          >
            删除
          </ConfirmButton>
        </Space>
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title="升级策略管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建策略
          </Button>
        }
      >
        <DataTable<MonitorEscalationPolicy>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText="暂无升级策略"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? '编辑升级策略' : '新建升级策略'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="策略名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：未确认告警 30 分钟升级" maxLength={128} />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="alert_type" label="匹配告警类型" style={{ flex: 1 }}>
              <Select placeholder="全部类型" options={ALERT_TYPE_OPTIONS} allowClear />
            </Form.Item>
            <Form.Item name="severity" label="匹配级别" style={{ flex: 1 }}>
              <Select placeholder="全部级别" options={SEVERITY_OPTIONS} allowClear />
            </Form.Item>
          </Space>

          <Divider titlePlacement="left" plain>
            多级升级链（可选）
          </Divider>
          <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
            配置后按步骤顺序渐进升级；留空则使用下方单级模式。
          </Text>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, idx) => (
                  <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="start">
                    <Tag color="gold">步骤{idx + 1}</Tag>
                    <Form.Item
                      {...field}
                      name={[field.name, 'wait_minutes']}
                      rules={[{ required: true, message: '必填' }]}
                      style={{ marginBottom: 0 }}
                    >
                      <InputNumber min={1} placeholder="等待分钟" style={{ width: 110 }} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_severity']}
                      style={{ marginBottom: 0 }}
                    >
                      <Select
                        placeholder="升级级别"
                        options={SEVERITY_OPTIONS}
                        allowClear
                        style={{ width: 120 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_to_role_id']}
                      style={{ marginBottom: 0 }}
                    >
                      <InputNumber min={1} placeholder="角色ID" style={{ width: 100 }} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'escalate_webhook_url']}
                      style={{ marginBottom: 0, flex: 1 }}
                    >
                      <Input
                        placeholder="webhook URL（可选）"
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
                    description="未配置多级链"
                    style={{ margin: '8px 0' }}
                  />
                )}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => add({ wait_minutes: 30, enabled: true })}
                  block
                >
                  添加升级步骤
                </Button>
              </>
            )}
          </Form.List>

          <Divider titlePlacement="left" plain>
            单级模式（无多级链时生效）
          </Divider>
          <Form.Item
            name="wait_minutes"
            label="未确认等待分钟数"
            rules={[{ required: true, message: '请输入等待分钟数' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} placeholder="如 30" />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="escalate_severity" label="升级后级别" style={{ flex: 1 }}>
              <Select placeholder="不升级级别" options={SEVERITY_OPTIONS} allowClear />
            </Form.Item>
            <Form.Item name="escalate_to_role_id" label="升级通知角色 ID" style={{ flex: 1 }}>
              <InputNumber min={1} style={{ width: '100%' }} placeholder="如 5（运维主管）" />
            </Form.Item>
          </Space>
          <Form.Item name="escalate_webhook_url" label="升级 Webhook URL（可选）">
            <Input placeholder="https://example.com/hook" maxLength={512} />
          </Form.Item>
          <Form.Item
            name="repeat_minutes"
            label="重复升级间隔分钟（0=只升一次）"
            extra="设为 N 时，每 N 分钟再次升级未确认告警"
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
