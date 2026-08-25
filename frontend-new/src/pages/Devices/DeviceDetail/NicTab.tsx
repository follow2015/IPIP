/**
 * 网卡端口标签页
 * - 网卡端口列表 + 编辑 + 批量删除
 * - 模板快速配置（复用 NicConfigFields 共用组件）
 * - 仅 server/other 设备
 */
import { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, InputNumber, Select, Popconfirm } from 'antd';
import { AppstoreOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useDeviceNics,
  useUpdateNic,
  useDeleteNic,
  useBatchCreateNics,
  useBatchDeleteNics
} from '@/services/device-nic';
import { useComponentTemplates } from '@/services/component-template';
import NicConfigFields, { expandNicPorts } from '@/components/NicConfigFields';
import StatusTag from '@/components/StatusTag';
import { useMessage } from '@/hooks/useMessage';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import { PORT_USAGE_STATUS_MAP } from '@/types/enums';
import type { DeviceNicPort } from '@/types/models';

interface NicTabProps {
  deviceId: number;
}


const PORT_TYPE_OPTIONS = [
  { label: 'RJ45 (电口)', value: 'RJ45' },
  { label: 'SFP (1G光口)', value: 'SFP' },
  { label: 'SFP+ (10G光口)', value: 'SFP+' },
  { label: 'SFP28 (25G光口)', value: 'SFP28' },
  { label: 'QSFP+ (40G光口)', value: 'QSFP+' },
  { label: 'QSFP28 (100G光口)', value: 'QSFP28' },
  { label: 'QSFP56 (200G光口)', value: 'QSFP56' },
  { label: 'QSFP-DD (400G光口)', value: 'QSFP-DD' }
];


const PORT_SPEED_OPTIONS = [
  { label: '100M', value: '100M' },
  { label: '1G', value: '1G' },
  { label: '10G', value: '10G' },
  { label: '25G', value: '25G' },
  { label: '40G', value: '40G' },
  { label: '100G', value: '100G' },
  { label: '400G', value: '400G' }
];


const PORT_STATUS_OPTIONS = [
  { label: '空闲', value: 'free' },
  { label: '占用', value: 'occupied' },
  { label: '禁用', value: 'disabled' }
];


function NicTab({ deviceId }: NicTabProps) {
  const { data: nics, isLoading } = useDeviceNics(deviceId);
  const updateNic = useUpdateNic(deviceId);
  const deleteNic = useDeleteNic(deviceId);
  const batchCreateNics = useBatchCreateNics(deviceId);
  const message = useMessage();

  
  const { data: nicTemplates = [] } = useComponentTemplates('nic');

  
  const [formOpen, setFormOpen] = useState(false);
  const [editingNic, setEditingNic] = useState<DeviceNicPort | null>(null);
  const [form] = Form.useForm();

  
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateForm] = Form.useForm();

  
  const batch = useBatchSelection<DeviceNicPort>({ dataSource: nics ?? [] });

  
  const batchDeleteNics = useBatchDeleteNics(deviceId);

  
  const handleEdit = (record: DeviceNicPort) => {
    setEditingNic(record);
    form.setFieldsValue(record);
    setFormOpen(true);
  };

  
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingNic) {
        await updateNic.mutateAsync({ portId: editingNic.id, data: values });
        message.success('更新成功');
      }
      setFormOpen(false);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleBatchDelete = async () => {
    if (batch.count === 0) return;
    try {
      const res = await batchDeleteNics.mutateAsync({ port_ids: batch.selectedKeys.map(Number) });
      const deleted = res.data?.deleted.length ?? 0;
      const skipped = res.data?.skipped.length ?? 0;
      message.success(`已删除 ${deleted} 个端口`);
      if (skipped > 0) {
        message.warning(`${skipped} 个端口因占用或无效被跳过`);
      }
      batch.clear();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '批量删除失败');
    }
  };

  
  const handleTemplateSubmit = async () => {
    try {
      await templateForm.validateFields();
    } catch {
      return;
    }
    const values = templateForm.getFieldsValue();
    const nicPortsFormVal = values.nic_ports as { template_id?: number }[] | undefined;
    const ports = expandNicPorts(nicPortsFormVal, nicTemplates);
    if (ports.length === 0) {
      message.warning('请至少选择一个网卡模板');
      return;
    }
    try {
      await batchCreateNics.mutateAsync({ ports });
      message.success(`已按模板创建 ${ports.length} 个端口`);
      setTemplateOpen(false);
      templateForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建失败');
    }
  };

  
  const columns = [
    { title: '显示名', dataIndex: 'display_name', key: 'display_name' },
    { title: '网卡号', dataIndex: 'nic_number', key: 'nic_number', width: 80 },
    { title: '端口号', dataIndex: 'port_number', key: 'port_number', width: 80 },
    {
      title: '端口名称',
      dataIndex: 'port_name',
      key: 'port_name',
      width: 120,
      render: (v: string) => v || '-'
    },
    {
      title: '端口类型',
      dataIndex: 'port_type',
      key: 'port_type',
      width: 90,
      render: (v: string) => v || '-'
    },
    {
      title: '速率',
      dataIndex: 'port_speed',
      key: 'port_speed',
      width: 80,
      render: (v: string) => v || '-'
    },
    {
      title: '端口状态',
      dataIndex: 'port_status',
      key: 'port_status',
      width: 90,
      render: (v: string) => <StatusTag status={v} statusMap={PORT_USAGE_STATUS_MAP} />
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (v: string) => v || '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: DeviceNicPort) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="确定删除该端口？"
            onConfirm={async () => {
              try {
                await deleteNic.mutateAsync(record.id);
                message.success('删除成功');
              } catch (err) {
                message.error(err instanceof Error ? err.message : '删除失败');
              }
            }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <div>
      {}
      <BatchActionBar count={batch.count} unit="个端口" onClear={batch.clear}>
        <Popconfirm title={`确定删除选中的 ${batch.count} 个端口？`} onConfirm={handleBatchDelete}>
          <Button danger icon={<DeleteOutlined />}>
            批量删除
          </Button>
        </Popconfirm>
      </BatchActionBar>

      {}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button
            icon={<AppstoreOutlined />}
            onClick={() => {
              setTemplateOpen(true);
              templateForm.resetFields();
            }}
          >
            模板配置
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={nics ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
        rowSelection={batch.rowSelection}
      />

      {}
      <Modal
        title="编辑端口"
        open={formOpen}
        onOk={handleSubmit}
        onCancel={() => setFormOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="nic_number"
            label="网卡号"
            rules={[{ required: true, message: '请输入网卡号' }]}
          >
            <InputNumber min={1} max={8} style={{ width: '100%' }} placeholder="网卡编号" />
          </Form.Item>
          <Form.Item
            name="port_number"
            label="端口号"
            rules={[{ required: true, message: '请输入端口号' }]}
          >
            <InputNumber min={1} max={16} style={{ width: '100%' }} placeholder="端口编号" />
          </Form.Item>
          <Form.Item name="port_name" label="端口名称">
            <Input placeholder="如 port1" />
          </Form.Item>
          <Form.Item name="port_type" label="端口类型">
            <Select placeholder="请选择" options={PORT_TYPE_OPTIONS} allowClear />
          </Form.Item>
          <Form.Item name="port_speed" label="速率">
            <Select placeholder="请选择" options={PORT_SPEED_OPTIONS} allowClear />
          </Form.Item>
          <Form.Item name="port_status" label="端口状态">
            <Select placeholder="请选择" options={PORT_STATUS_OPTIONS} allowClear />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {}
      <Modal
        title="模板配置"
        open={templateOpen}
        onCancel={() => setTemplateOpen(false)}
        onOk={handleTemplateSubmit}
        okText={`确认创建`}
        confirmLoading={batchCreateNics.isPending}
        width={700}
        destroyOnHidden
      >
        <Form form={templateForm} layout="vertical" autoComplete="off">
          <NicConfigFields form={templateForm} />
        </Form>
      </Modal>
    </div>
  );
}

export default NicTab;
