/**
 * G4.3: 设备级阈值覆盖管理页
 *
 * 按 (device_id, metric_key) 覆盖全局默认阈值，
 * 用于个别设备需要更严格/宽松阈值的场景（如高温机房、关键设备）。
 *
 * P1-4: 阈值表单结构化，复用 MetricTemplates/shared.tsx 的
 * buildThreshold/parseThreshold/renderThreshold，按 metric_type 动态渲染。
 */
import { useMemo, useState } from 'react';
import {
  Card,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Typography,
  Row,
  Col
} from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import {
  useThresholdOverrides,
  useUpsertThresholdOverride,
  useDeleteThresholdOverride,
  useMetricTemplates,
  type DeviceMetricOverride,
  type DeviceMetricOverrideInput
} from '@/services/monitor';
import {
  buildThreshold,
  parseThreshold,
  renderThreshold,
  METRIC_TYPE_OPTIONS,
  type MetricTemplateFormValues
} from '../MetricTemplates/shared';
import { formatDateTime } from '@/utils/format';

const { Text } = Typography;

interface OverrideFormValues {
  device_id: number;
  metric_key: string;
  metric_type: string;
  enabled: boolean;
  note?: string;
  warn?: number;
  crit?: number;
  expected?: string;
  threshold_json?: string;
}

export default function ThresholdOverridesPage() {
  const { data, isLoading } = useThresholdOverrides();
  const upsertMut = useUpsertThresholdOverride();
  const deleteMut = useDeleteThresholdOverride();
  const { data: templatesData } = useMetricTemplates();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DeviceMetricOverride | null>(null);
  const [form] = Form.useForm<OverrideFormValues>();
  const table = useTable({ initialPerPage: 20 });
  const message = useMessage();

  const items: DeviceMetricOverride[] = data?.items ?? [];

  const metricTypeMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of templatesData?.items ?? []) {
      if (t.enabled && t.metric_key && t.metric_type && !m.has(t.metric_key)) {
        m.set(t.metric_key, t.metric_type);
      }
    }
    return m;
  }, [templatesData]);

  const resolveMetricType = (metricKey: string): string => metricTypeMap.get(metricKey) ?? 'gauge';

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, metric_type: 'gauge' });
    setModalOpen(true);
  };

  const openEdit = (record: DeviceMetricOverride) => {
    setEditing(record);
    const mt = resolveMetricType(record.metric_key);
    form.setFieldsValue({
      device_id: record.device_id,
      metric_key: record.metric_key,
      metric_type: mt,
      enabled: record.enabled,
      note: record.note ?? undefined,
      ...parseThreshold(record.threshold, mt)
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const formValues = {
        device_type: '',
        source: 'snmp',
        ...values
      } as MetricTemplateFormValues;
      if (values.metric_type === 'event' && values.threshold_json) {
        try {
          JSON.parse(values.threshold_json);
        } catch {
          message.error('阈值 JSON 格式不合法，请检查');
          return;
        }
      }
      const thresholdObj = buildThreshold(formValues);
      if (!thresholdObj) {
        message.error('请至少配置一个阈值字段');
        return;
      }
      const payload: DeviceMetricOverrideInput = {
        device_id: values.device_id,
        metric_key: values.metric_key,
        threshold: thresholdObj,
        enabled: values.enabled,
        note: values.note
      };
      await upsertMut.mutateAsync(payload);
      message.success(editing ? '已更新' : '已创建');
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
      title: '设备 ID',
      dataIndex: 'device_id',
      key: 'device_id'
    },
    {
      title: '指标',
      dataIndex: 'metric_key',
      key: 'metric_key',
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '阈值',
      dataIndex: 'threshold',
      key: 'threshold',
      render: (v: Record<string, unknown>, record: DeviceMetricOverride) =>
        renderThreshold(v, resolveMetricType(record.metric_key))
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag>)
    },
    {
      title: '备注',
      dataIndex: 'note',
      key: 'note',
      ellipsis: true
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => <Text type="secondary">{formatDateTime(v)}</Text>
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: DeviceMetricOverride) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该阈值覆盖吗？删除后回退到全局模板。"
            onConfirm={() => handleDelete(r.id)}
          >
            删除
          </ConfirmButton>
        </Space>
      )
    }
  ];

  const currentMetricType = Form.useWatch('metric_type', form) ?? 'gauge';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title="设备级阈值覆盖"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建覆盖
          </Button>
        }
      >
        <DataTable<DeviceMetricOverride>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText="暂无阈值覆盖"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? '编辑阈值覆盖' : '新建阈值覆盖'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={upsertMut.isPending}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="device_id"
                label="设备 ID"
                rules={[{ required: true, message: '请输入设备 ID' }]}
              >
                <InputNumber style={{ width: '100%' }} min={1} disabled={!!editing} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="metric_key"
                label="指标标识"
                rules={[{ required: true, message: '请输入指标标识' }]}
              >
                <Input placeholder="如 temperature / disk_failure" disabled={!!editing} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="metric_type"
            label="指标类型"
            tooltip="决定阈值字段结构。编辑时自动从关联模板读取，可手动调整"
          >
            <Select options={METRIC_TYPE_OPTIONS} />
          </Form.Item>

          {/* 结构化阈值：按 metric_type 动态渲染（复用 MetricTemplateModal 模式） */}
          {(currentMetricType === 'gauge' || currentMetricType === 'counter') && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="告警阈值 (warn)" name="warn" tooltip="达到该值触发告警">
                  <InputNumber style={{ width: '100%' }} placeholder="如 60" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="严重阈值 (crit)" name="crit" tooltip="达到该值触发严重告警">
                  <InputNumber style={{ width: '100%' }} placeholder="如 70" />
                </Form.Item>
              </Col>
            </Row>
          )}
          {currentMetricType === 'state' && (
            <Form.Item label="期望值 (expected)" name="expected" tooltip="实际值不等于该值时告警">
              <Input placeholder="如 up / 1" />
            </Form.Item>
          )}
          {currentMetricType === 'event' && (
            <Form.Item
              label="阈值 JSON"
              name="threshold_json"
              tooltip="事件类型阈值，自由 JSON 结构"
            >
              <Input.TextArea placeholder={'{\n  "pattern": "error"\n}'} rows={3} />
            </Form.Item>
          )}

          <Form.Item name="note" label="备注">
            <Input placeholder="如：高温机房，阈值上调" maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
