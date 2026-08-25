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
  const { data, isLoading } = useAlertDependencyRules();
  const createMut = useCreateAlertDependencyRule();
  const updateMut = useUpdateAlertDependencyRule();
  const deleteMut = useDeleteAlertDependencyRule();
  const [modalOpen, setModalOpen] = useState(false);
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
    setModalOpen(true);
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
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (values.upstream_device_id === values.downstream_device_id) {
        message.error('上游与下游设备不能相同');
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
      render: (v: string, r: MonitorAlertDependencyRule) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">已停用</Tag>}
        </Space>
      )
    },
    {
      title: '上游设备 ID',
      dataIndex: 'upstream_device_id',
      key: 'upstream_device_id',
      render: (v: number) => <Tag color="red">{v}</Tag>
    },
    {
      title: '下游设备 ID',
      dataIndex: 'downstream_device_id',
      key: 'downstream_device_id',
      render: (v: number) => <Tag color="orange">{v}</Tag>
    },
    {
      title: '告警类型',
      dataIndex: 'alert_types',
      key: 'alert_types',
      render: (v: string[] | null) =>
        v === null || v.length === 0 ? (
          <Tag color="blue">全部类型</Tag>
        ) : (
          v.map((t) => <Tag key={t}>{t}</Tag>)
        )
    },
    {
      title: '说明',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: MonitorAlertDependencyRule) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该依赖抑制规则吗？此操作不可恢复。"
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
      <Alert
        type="info"
        showIcon
        message="自动拓扑抑制 + 手动规则"
        description="系统自动基于设备父子拓扑（DeviceServerExt.parent_device_id）抑制下游告警：父设备有 active 告警时，子设备同类型告警自动抑制。本页规则用于手动覆盖或补充自动推断（如网络设备间的依赖）。"
      />
      <Card
        title="告警依赖抑制规则"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建规则
          </Button>
        }
      >
        <DataTable<MonitorAlertDependencyRule>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText="暂无依赖抑制规则"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? '编辑依赖抑制规则' : '新建依赖抑制规则'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：核心交换机→接入交换机依赖" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="upstream_device_id"
            label="上游设备 ID"
            rules={[{ required: true, message: '请输入上游设备 ID' }]}
          >
            <InputNumber placeholder="如：1" style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item
            name="downstream_device_id"
            label="下游设备 ID"
            rules={[{ required: true, message: '请输入下游设备 ID' }]}
          >
            <InputNumber placeholder="如：2" style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="alert_types" label="受抑制告警类型（留空=全部类型）">
            <Select
              mode="multiple"
              placeholder="选择告警类型（留空=全部）"
              options={ALERT_TYPE_OPTIONS}
              allowClear
            />
          </Form.Item>
          <Form.Item name="reason" label="规则说明">
            <Input.TextArea
              rows={2}
              placeholder="如：核心交换机 down 时抑制下游接入交换机告警"
              maxLength={255}
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
