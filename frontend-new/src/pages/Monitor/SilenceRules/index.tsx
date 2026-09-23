/**
 * G4.1: 静默规则管理页
 *
 * 在指定时间窗口内对匹配的设备/告警类型静默（不入箱、不推送），
 * 用于计划内维护、已知问题处理等场景避免告警噪声。
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
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { data, isLoading } = useSilenceRules();
  const createMut = useCreateSilenceRule();
  const updateMut = useUpdateSilenceRule();
  const deleteMut = useDeleteSilenceRule();
  const modal = useDisclosure();
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
    modal.open();
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
    modal.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!values.range || values.range.length !== 2) {
        message.error(t('silence.validation.windowRequired'));
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
      render: (v: string, r: MonitorSilenceRule) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">{t('credential.status.disabled')}</Tag>}
        </Space>
      )
    },
    {
      title: t('silence.column.deviceScope'),
      dataIndex: 'device_ids',
      key: 'device_ids',
      render: (v: number[] | null) =>
        v === null || v.length === 0 ? (
          <Tag color="blue">{t('silence.allDevices')}</Tag>
        ) : (
          `${v.length} ${t('stat.unitDevice', { count: v.length })}`
        )
    },
    {
      title: t('column.alertType'),
      dataIndex: 'alert_type',
      key: 'alert_type',
      render: (v: string[] | null) =>
        v === null || v.length === 0 ? (
          <Tag color="blue">{t('escalation.matchAllTypes')}</Tag>
        ) : (
          v.map((t) => <Tag key={t}>{t}</Tag>)
        )
    },
    {
      title: t('silence.column.window'),
      key: 'window',
      render: (_: unknown, r: MonitorSilenceRule) => (
        <Text type="secondary">
          {formatDateTime(r.silence_from)} ~ {formatDateTime(r.silence_until)}
        </Text>
      )
    },
    {
      title: t('silence.column.reason'),
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true
    },
    {
      title: t('silence.column.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by'
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: MonitorSilenceRule) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            {tc('action.edit')}
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={t('silence.confirm.deleteContent')}
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
        message={t('silence.alert.title')}
        description={t('silence.alert.description')}
      />
      <Card
        title={t('silence.title')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('silence.action.create')}
          </Button>
        }
      >
        <DataTable<MonitorSilenceRule>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText={t('silence.empty')}
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? t('silence.modal.editTitle') : t('silence.modal.createTitle')}
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
            label={t('silence.field.name')}
            rules={[
              { required: true, message: tc('validation.inputRequiredField', { field: tc('field.name') }) }
            ]}
          >
            <Input placeholder={t('silence.placeholder.name')} maxLength={128} />
          </Form.Item>
          <Form.Item
            name="range"
            label={t('silence.field.window')}
            rules={[{ required: true, message: t('silence.validation.windowPickerRequired') }]}
          >
            <RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="device_ids" label={t('silence.field.deviceIds')}>
            <Input placeholder={t('silence.placeholder.deviceIds')} />
          </Form.Item>
          <Form.Item name="alert_types" label={t('silence.field.alertTypes')}>
            <Select
              mode="multiple"
              placeholder={t('placeholder.alertTypesOptional')}
              options={ALERT_TYPE_OPTIONS}
              allowClear
            />
          </Form.Item>
          <Form.Item name="reason" label={t('silence.field.reason')}>
            <Input.TextArea rows={2} placeholder={t('silence.placeholder.reason')} maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
