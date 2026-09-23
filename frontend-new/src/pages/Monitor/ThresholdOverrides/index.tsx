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
  buildMetricTypeOptions,
  type MetricTemplateFormValues
} from '../MetricTemplates/shared';
import { formatDateTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';

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
  const modal = useDisclosure();
  const [editing, setEditing] = useState<DeviceMetricOverride | null>(null);
  const [form] = Form.useForm<OverrideFormValues>();
  const table = useTable({ initialPerPage: 20 });
  const message = useMessage();
  const { t: tm } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');

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
    modal.open();
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
    modal.open();
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
          message.error(tm('metricTemplate.message.invalidThresholdJson'));
          return;
        }
      }
      const thresholdObj = buildThreshold(formValues);
      if (!thresholdObj) {
        message.error(tm('thresholdOverride.message.thresholdRequired'));
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
      message.success(
        editing ? tm('thresholdOverride.message.updated') : tm('thresholdOverride.message.created')
      );
      modal.close();
    } catch (err: unknown) {
      if (err instanceof Error && err.message) message.error(err.message);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success(tm('thresholdOverride.message.deleted'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const columns = [
    {
      title: tm('thresholdOverride.column.deviceId'),
      dataIndex: 'device_id',
      key: 'device_id'
    },
    {
      title: tm('metricTemplate.column.metric'),
      dataIndex: 'metric_key',
      key: 'metric_key',
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: tm('metricTemplate.column.threshold'),
      dataIndex: 'threshold',
      key: 'threshold',
      render: (v: Record<string, unknown>, record: DeviceMetricOverride) =>
        renderThreshold(v, resolveMetricType(record.metric_key), tm)
    },
    {
      title: tc('action.enable'),
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean) =>
        v ? (
          <Tag color="green">{tm('metricTemplate.status.enabled')}</Tag>
        ) : (
          <Tag color="default">{tm('metricTemplate.status.disabled')}</Tag>
        )
    },
    {
      title: tc('field.remarks'),
      dataIndex: 'note',
      key: 'note',
      ellipsis: true
    },
    {
      title: tc('field.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => <Text type="secondary">{formatDateTime(v)}</Text>
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: DeviceMetricOverride) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            {tc('action.edit')}
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={tm('thresholdOverride.confirm.deleteContent')}
            onConfirm={() => handleDelete(r.id)}
          >
            {tc('action.delete')}
          </ConfirmButton>
        </Space>
      )
    }
  ];

  const currentMetricType = Form.useWatch('metric_type', form) ?? 'gauge';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title={tm('thresholdOverride.title')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {tm('thresholdOverride.action.create')}
          </Button>
        }
      >
        <DataTable<DeviceMetricOverride>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText={tm('thresholdOverride.empty')}
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={
          editing
            ? tm('thresholdOverride.modal.editTitle')
            : tm('thresholdOverride.modal.createTitle')
        }
        open={modal.isOpen}
        onOk={handleSubmit}
        onCancel={() => modal.close()}
        confirmLoading={upsertMut.isPending}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="device_id"
                label={tm('thresholdOverride.field.deviceId')}
                rules={[
                  { required: true, message: tm('thresholdOverride.validation.deviceIdRequired') }
                ]}
              >
                <InputNumber style={{ width: '100%' }} min={1} disabled={!!editing} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="metric_key"
                label={tm('thresholdOverride.field.metricKey')}
                rules={[
                  { required: true, message: tm('thresholdOverride.validation.metricKeyRequired') }
                ]}
              >
                <Input
                  placeholder={tm('thresholdOverride.placeholder.metricKey')}
                  disabled={!!editing}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="metric_type"
            label={tm('thresholdOverride.field.metricType')}
            tooltip={tm('thresholdOverride.tooltip.metricType')}
          >
            <Select options={buildMetricTypeOptions(tm)} />
          </Form.Item>

          {/* 结构化阈值：按 metric_type 动态渲染（复用 MetricTemplateModal 模式） */}
          {(currentMetricType === 'gauge' || currentMetricType === 'counter') && (
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item
                  label={tm('metricTemplate.field.warn')}
                  name="warn"
                  tooltip={tm('metricTemplate.tooltip.warn')}
                >
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder={tm('metricTemplate.placeholder.warn')}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item
                  label={tm('metricTemplate.field.crit')}
                  name="crit"
                  tooltip={tm('metricTemplate.tooltip.crit')}
                >
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder={tm('metricTemplate.placeholder.crit')}
                  />
                </Form.Item>
              </Col>
            </Row>
          )}
          {currentMetricType === 'state' && (
            <Form.Item
              label={tm('metricTemplate.field.expected')}
              name="expected"
              tooltip={tm('metricTemplate.tooltip.expected')}
            >
              <Input placeholder={tm('metricTemplate.placeholder.expected')} />
            </Form.Item>
          )}
          {currentMetricType === 'event' && (
            <Form.Item
              label={tm('metricTemplate.field.thresholdJson')}
              name="threshold_json"
              tooltip={tm('metricTemplate.tooltip.thresholdJson')}
            >
              <Input.TextArea placeholder={'{\n  "pattern": "error"\n}'} rows={3} />
            </Form.Item>
          )}

          <Form.Item name="note" label={tc('field.remarks')}>
            <Input placeholder={tm('thresholdOverride.placeholder.note')} maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
