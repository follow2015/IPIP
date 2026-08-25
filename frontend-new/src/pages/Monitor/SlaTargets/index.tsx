/**
 * P2-13: SLA/SLO 监控目标管理 + 达成度报表
 *
 * 定义设备/设备组的可用率 SLA 目标，基于 device_monitor_timeseries_hourly
 * 的 reachable 聚合计算实际达成度。
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

const { Text } = Typography;

export default function SlaTargetsPage() {
  const { data, isLoading } = useSlaTargets();
  const { data: achievementsData } = useSlaAchievements();
  const createMut = useCreateSlaTarget();
  const updateMut = useUpdateSlaTarget();
  const deleteMut = useDeleteSlaTarget();
  const [modalOpen, setModalOpen] = useState(false);
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
    setModalOpen(true);
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
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const deviceIds = (values.target_device_ids as string)
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !Number.isNaN(n));
      if (deviceIds.length === 0) {
        message.error('请输入至少一个设备 ID');
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
      render: (v: string, r: MonitorSlaTarget) => (
        <Space>
          <Text strong>{v}</Text>
          {!r.enabled && <Tag color="default">已停用</Tag>}
        </Space>
      )
    },
    {
      title: '目标设备',
      dataIndex: 'target_device_ids',
      key: 'target_device_ids',
      render: (v: number[]) => `${v.length} 台`
    },
    {
      title: '可用率目标',
      dataIndex: 'target_ratio',
      key: 'target_ratio',
      render: (v: number) => <Tag color="blue">{(v * 100).toFixed(2)}%</Tag>
    },
    {
      title: '评估窗口',
      dataIndex: 'window_days',
      key: 'window_days',
      render: (v: number) => `${v} 天`
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: MonitorSlaTarget) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <ConfirmButton
            type="link"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该 SLA 目标吗？此操作不可恢复。"
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
        message="SLA/SLO 监控"
        description="定义设备/设备组的可用率 SLA 目标，系统基于探测时序小时聚合（device_monitor_timeseries_hourly 的 reachable 指标）计算实际达成度。"
      />

      <Card title="SLA 达成度报表">
        {achievements.length === 0 ? (
          <Text type="secondary">暂无启用的 SLA 目标</Text>
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
                      title="实际可用率"
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
                      format={() => `目标 ${targetPct.toFixed(2)}%`}
                      size="small"
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      样本数: {a.sample_count} | 窗口: {a.window_start?.slice(0, 10)} ~{' '}
                      {a.window_end?.slice(0, 10)}
                    </Text>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Card>

      <Card
        title="SLA 目标管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建目标
          </Button>
        }
      >
        <DataTable<MonitorSlaTarget>
          columns={columns}
          dataSource={items}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          total={items.length}
          emptyText="暂无 SLA 目标"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <Modal
        title={editing ? '编辑 SLA 目标' : '新建 SLA 目标'}
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
            label="目标名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：核心设备月度可用率 SLA" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="target_device_ids"
            label="目标设备 ID（逗号分隔）"
            rules={[{ required: true, message: '请输入设备 ID' }]}
          >
            <Input placeholder="如：1,2,3" />
          </Form.Item>
          <Form.Item
            name="target_ratio"
            label="可用率目标（0~1，如 0.99=99%）"
            rules={[{ required: true, message: '请输入可用率目标' }]}
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
            label="评估窗口（天）"
            rules={[{ required: true, message: '请输入评估窗口' }]}
          >
            <InputNumber placeholder="30" style={{ width: '100%' }} min={1} max={365} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="如：月度可用率 ≥ 99%" maxLength={255} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
