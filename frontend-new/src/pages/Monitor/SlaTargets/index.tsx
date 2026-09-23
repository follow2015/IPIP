/**
 * P2-13: SLA/SLO 监控目标管理 + 达成度报表
 *
 * 定义设备/设备组的可用率 SLA 目标，基于 device_monitor_timeseries_hourly
 * 的 reachable 聚合计算实际达成度。
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
  Typography,
  Alert,
  Statistic,
  Row,
  Col,
  Progress
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import {
  useSlaTargets,
  useCreateSlaTarget,
  useUpdateSlaTarget,
  useDeleteSlaTarget,
  useSlaAchievements,
  type MonitorSlaTarget,
  type MonitorSlaTargetInput
} from '@/services/monitor';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

export default function SlaTargetsPage() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { data, isLoading } = useSlaTargets();
  const { data: achievementsData } = useSlaAchievements();
  const createMut = useCreateSlaTarget();
  const updateMut = useUpdateSlaTarget();
  const deleteMut = useDeleteSlaTarget();
  const modal = useDisclosure();
  const [editing, setEditing] = useState<MonitorSlaTarget | null>(null);
  const message = useMessage();
  const [form] = Form.useForm<{
    name: string;
    target_device_ids: string;
    target_ratio: number;
    window_days: number;
    description?: string;
    enabled?: boolean;
  }>();
  const table = useTable({ initialPerPage: 20 });

  const items: MonitorSlaTarget[] = data?.items ?? [];
  const achievements = achievementsData?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, window_days: 30, target_ratio: 0.99 });
    modal.open();
  };

  const openEdit = (record: MonitorSlaTarget) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      target_device_ids: record.target_device_ids ? record.target_device_ids.join(',') : '',
      target_ratio: record.target_ratio,
      window_days: record.window_days,
      description: record.description ?? undefined,
      enabled: record.enabled
    });
    modal.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const deviceIds = (values.target_device_ids as string)
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !Number.isNaN(n));
      if (deviceIds.length === 0) {
        message.error(t('sla.validation.deviceIdsRequired'));
        return;
      }
      const payload: MonitorSlaTargetInput = {
        name: values.name,
        target_device_ids: deviceIds,
        target_ratio: values.target_ratio,
        window_days: values.window_days,
        description: values.description,
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
      render: (v: string, r: MonitorSlaTarget) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">{t('credential.status.disabled')}</Tag>}
        </Space>
      )
    },
    {
      title: t('sla.column.targetDevices'),
      dataIndex: 'target_device_ids',
      key: 'target_device_ids',
      render: (v: number[]) => `${v.length} ${t('stat.unitDevice', { count: v.length })}`
    },
    {
      title: t('sla.column.targetRatio'),
      dataIndex: 'target_ratio',
      key: 'target_ratio',
      render: (v: number) => <Tag color="blue">{(v * 100).toFixed(2)}%</Tag>
    },
    {
      title: t('sla.column.window'),
      dataIndex: 'window_days',
      key: 'window_days',
      render: (v: number) => t('sla.windowDays', { count: v })
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: MonitorSlaTarget) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            {tc('action.edit')}
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={t('sla.confirm.deleteContent')}
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
        message={t('sla.alert.title')}
        description={t('sla.alert.description')}
      />

      <Card title={t('sla.achievementTitle')}>
        {achievements.length === 0 ? (
          <Text type="secondary">{t('sla.achievementEmpty')}</Text>
        ) : (
          <Row gutter={[16, 16]}>
            {achievements.map((a) => {
              const actualPct =
                a.actual_ratio !== null && a.actual_ratio !== undefined
                  ? a.actual_ratio * 100
                  : null;
              const targetPct = (a.target_ratio ?? 0) * 100;
              return (
                <Col xs={24} sm={12} md={8} key={a.target_id}>
                  <Card size="small" title={a.name}>
                    <Statistic
                      title={t('sla.stat.actualRatio')}
                      value={actualPct !== null ? actualPct.toFixed(2) : '—'}
                      suffix={actualPct !== null ? '%' : ''}
                      prefix={
                        a.met_sla ? (
                          <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        ) : (
                          <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                        )
                      }
                    />
                    <Progress
                      percent={actualPct ?? 0}
                      success={{ percent: a.met_sla ? (actualPct ?? 0) : 0 }}
                      status={a.met_sla ? 'success' : 'exception'}
                      format={() => t('sla.stat.targetAt', { pct: targetPct.toFixed(2) })}
                      size="small"
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t('sla.stat.sampleSummary', {
                        count: a.sample_count,
                        start: a.window_start?.slice(0, 10),
                        end: a.window_end?.slice(0, 10)
                      })}
                    </Text>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Card>

      <Card
        title={t('sla.title')}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('sla.action.create')}
          </Button>
        }
      >
        <DataTable<MonitorSlaTarget>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText={t('sla.empty')}
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? t('sla.modal.editTitle') : t('sla.modal.createTitle')}
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
            label={t('sla.field.name')}
            rules={[
              { required: true, message: tc('validation.inputRequiredField', { field: tc('field.name') }) }
            ]}
          >
            <Input placeholder={t('sla.placeholder.name')} maxLength={128} />
          </Form.Item>
          <Form.Item
            name="target_device_ids"
            label={t('sla.field.targetDeviceIds')}
            rules={[{ required: true, message: t('thresholdOverride.validation.deviceIdRequired') }]}
          >
            <Input placeholder={t('sla.placeholder.deviceIds')} />
          </Form.Item>
          <Form.Item
            name="target_ratio"
            label={t('sla.field.targetRatio')}
            rules={[{ required: true, message: t('sla.validation.targetRatioRequired') }]}
          >
            <InputNumber
              placeholder="0.99"
              style={{ width: '100%' }}
              min={0.0001}
              max={1}
              step={0.001}
            />
          </Form.Item>
          <Form.Item
            name="window_days"
            label={t('sla.field.windowDays')}
            rules={[{ required: true, message: t('sla.validation.windowDaysRequired') }]}
          >
            <InputNumber placeholder="30" style={{ width: '100%' }} min={1} max={365} />
          </Form.Item>
          <Form.Item name="description" label={tc('field.description')}>
            <Input.TextArea rows={2} placeholder={t('sla.placeholder.description')} maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
