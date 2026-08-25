/**
 * G4.1: 静默规则管理页
 *
 * 在指定时间窗口内对匹配的设备/告警类型静默（不入箱、不推送），
 * 用于计划内维护、已知问题处理等场景避免告警噪声。
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
  Switch,
  DatePicker,
  Select,
  Typography,
  Alert
} from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import dayjs from 'dayjs';
import { ensureUtc } from '@/utils/format';
import {
  useSilenceRules,
  useCreateSilenceRule,
  useUpdateSilenceRule,
  useDeleteSilenceRule,
  type MonitorSilenceRule,
  type MonitorSilenceRuleInput
} from '@/services/monitor';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;
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

export default function SilenceRulesPage() {
  const { data, isLoading } = useSilenceRules();
  const createMut = useCreateSilenceRule();
  const updateMut = useUpdateSilenceRule();
  const deleteMut = useDeleteSilenceRule();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MonitorSilenceRule | null>(null);
  const message = useMessage();
  const [form] = Form.useForm<{
    name: string;
    device_ids: string;
    alert_types?: string[];
    range?: [dayjs.Dayjs, dayjs.Dayjs];
    reason?: string;
    enabled?: boolean;
  }>();
  const table = useTable({ initialPerPage: 20 });

  const items: MonitorSilenceRule[] = data?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true });
    setModalOpen(true);
  };

  const openEdit = (record: MonitorSilenceRule) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      device_ids: record.device_ids ? record.device_ids.join(',') : '',
      alert_types: record.alert_type ?? undefined,
      reason: record.reason ?? undefined,
      enabled: record.enabled,
      range: [dayjs(ensureUtc(record.silence_from)), dayjs(ensureUtc(record.silence_until))]
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!values.range || values.range.length !== 2) {
        message.error('请选择静默时间窗口');
        return;
      }
      let deviceIds: number[] | null = null;
      if (typeof values.device_ids === 'string' && (values.device_ids as string).trim()) {
        deviceIds = (values.device_ids as string)
          .split(',')
          .map((s) => parseInt(s.trim(), 10))
          .filter((n) => !Number.isNaN(n));
      }
      const payload: MonitorSilenceRuleInput = {
        name: values.name,
        device_ids: deviceIds,
        alert_types: values.alert_types ?? null,
        silence_from: values.range[0].toISOString(),
        silence_until: values.range[1].toISOString(),
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
      render: (v: string, r: MonitorSilenceRule) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">已停用</Tag>}
        </Space>
      )
    },
    {
      title: '设备范围',
      dataIndex: 'device_ids',
      key: 'device_ids',
      render: (v: number[] | null) =>
        v === null || v.length === 0 ? <Tag color="blue">全部设备</Tag> : `${v.length} 台`
    },
    {
      title: '告警类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      render: (v: string[] | null) =>
        v === null || v.length === 0 ? (
          <Tag color="blue">全部类型</Tag>
        ) : (
          v.map((t) => <Tag key={t}>{t}</Tag>)
        )
    },
    {
      title: '静默窗口',
      key: 'window',
      render: (_: unknown, r: MonitorSilenceRule) => (
        <Text type="secondary">
          {formatDateTime(r.silence_from)} ~ {formatDateTime(r.silence_until)}
        </Text>
      )
    },
    {
      title: '原因',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      key: 'created_by'
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: MonitorSilenceRule) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该静默规则吗？此操作不可恢复。"
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
        message="维护模式自动静默"
        description="设备状态为「维护中」时，系统自动跳过该设备的告警生成（连通性告警 + 指标告警均静默），但仍会采集指标数据供维护后对比。无需在此手动创建静默规则。"
      />
      <Card
        title="静默规则管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建规则
          </Button>
        }
      >
        <DataTable<MonitorSilenceRule>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText="暂无静默规则"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? '编辑静默规则' : '新建静默规则'}
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
            <Input placeholder="如：核心交换机维护窗口" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="range"
            label="静默时间窗口"
            rules={[{ required: true, message: '请选择时间窗口' }]}
          >
            <RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="device_ids" label="静默设备 ID（逗号分隔，留空=全部设备）">
            <Input placeholder="如：1,2,3（留空表示全部设备）" />
          </Form.Item>
          <Form.Item name="alert_types" label="静默告警类型（留空=全部类型）">
            <Select
              mode="multiple"
              placeholder="选择告警类型（留空=全部）"
              options={ALERT_TYPE_OPTIONS}
              allowClear
            />
          </Form.Item>
          <Form.Item name="reason" label="静默原因">
            <Input.TextArea rows={2} placeholder="如：计划内维护" maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
