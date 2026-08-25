/**
 * 存储标签页
 * - 存储列表 + 编辑 + 批量删除
 * - 模板快速配置（复用 HardwareConfigFields 存储配置部分）
 * - 按存储类型容量汇总
 */
import { useState, useMemo } from 'react';
import {
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Tag,
  Divider,
  Popconfirm
} from 'antd';
import { AppstoreOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useDeviceStorageDetail,
  useCreateStorage,
  useUpdateStorage,
  useDeleteStorage,
  useBatchDeleteStorage
} from '@/services/device-storage';
import HardwareConfigFields, {
  buildStorageList,
  type StorageItem
} from '@/components/HardwareConfigFields';
import { useMessage } from '@/hooks/useMessage';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import type { DeviceStorageDetail } from '@/types/models';

interface StorageTabProps {
  deviceId: number;
}


function formatGb(gb: number): string {
  if (gb >= 1024) return `${(gb / 1024).toFixed(1)}TB`;
  return `${Math.round(gb)}GB`;
}


function StorageTab({ deviceId }: StorageTabProps) {
  const { data: storageList, isLoading } = useDeviceStorageDetail(deviceId);
  const createStorage = useCreateStorage(deviceId);
  const updateStorage = useUpdateStorage(deviceId);
  const deleteStorage = useDeleteStorage(deviceId);
  const message = useMessage();

  
  const [formOpen, setFormOpen] = useState(false);
  const [editingStorage, setEditingStorage] = useState<DeviceStorageDetail | null>(null);
  const [form] = Form.useForm();

  
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateForm] = Form.useForm();

  
  const details: DeviceStorageDetail[] = useMemo(() => storageList ?? [], [storageList]);

  
  const batch = useBatchSelection<DeviceStorageDetail>({ dataSource: details });

  
  const batchDeleteStorage = useBatchDeleteStorage(deviceId);

  
  const handleEdit = (record: DeviceStorageDetail) => {
    setEditingStorage(record);
    form.setFieldsValue(record);
    setFormOpen(true);
  };

  
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingStorage) {
        await updateStorage.mutateAsync({ storageId: editingStorage.id, data: values });
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
      const res = await batchDeleteStorage.mutateAsync({
        storage_ids: batch.selectedKeys.map(Number)
      });
      const deleted = res.data?.deleted.length ?? 0;
      message.success(`已删除 ${deleted} 条存储`);
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
    const storageItems = values.storage_items as StorageItem[] | undefined;
    const list = buildStorageList(storageItems);
    if (list.length === 0) {
      message.warning('请至少配置一项存储');
      return;
    }
    try {
      for (const item of list) {
        await createStorage.mutateAsync(item);
      }
      message.success(`已按模板创建 ${list.length} 条存储`);
      setTemplateOpen(false);
      templateForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建失败');
    }
  };

  
  const storageSummary = useMemo(() => {
    if (details.length === 0) return null;
    let totalGb = 0;
    const byType: Record<string, { count: number; totalGb: number }> = {};
    for (const item of details) {
      const gb = item.capacity_gb ?? 0;
      totalGb += gb;
      const type = item.storage_type || '未知';
      if (!byType[type]) byType[type] = { count: 0, totalGb: 0 };
      byType[type].count += 1;
      byType[type].totalGb += gb;
    }
    return { totalGb, byType };
  }, [details]);

  
  const columns = [
    {
      title: '类型',
      dataIndex: 'storage_type',
      key: 'storage_type',
      width: 80,
      render: (v: string) => (
        <Tag color={v === 'SSD' ? 'blue' : v === 'NVMe' ? 'green' : 'orange'}>{v}</Tag>
      )
    },
    { title: '容量', dataIndex: 'capacity', key: 'capacity', width: 80 },
    {
      title: '接口类型',
      dataIndex: 'interface_type',
      key: 'interface_type',
      width: 80,
      render: (v: string) => v || '-'
    },
    {
      title: '插槽号',
      dataIndex: 'slot_number',
      key: 'slot_number',
      width: 70,
      render: (v: number) => v ?? '-'
    },
    {
      title: '厂商',
      dataIndex: 'manufacturer',
      key: 'manufacturer',
      width: 100,
      render: (v: string) => v || '-'
    },
    {
      title: '型号',
      dataIndex: 'model',
      key: 'model',
      width: 100,
      render: (v: string) => v || '-'
    },
    {
      title: '序列号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 120,
      render: (v: string) => v || '-'
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 70,
      render: (v: string) => {
        const map: Record<string, { color: string; label: string }> = {
          normal: { color: 'green', label: '正常' },
          fault: { color: 'red', label: '故障' },
          warning: { color: 'orange', label: '预警' }
        };
        const info = map[v];
        return info ? <Tag color={info.color}>{info.label}</Tag> : v || '-';
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: DeviceStorageDetail) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="确定删除该存储？"
            onConfirm={async () => {
              try {
                await deleteStorage.mutateAsync(record.id);
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
      {storageSummary && storageSummary.totalGb > 0 && (
        <div
          style={{
            marginBottom: 16,
            padding: '10px 16px',
            background: '#fafafa',
            borderRadius: 6,
            border: '1px solid #f0f0f0'
          }}
        >
          <span style={{ fontWeight: 500, fontSize: 14 }}>
            总容量：{formatGb(storageSummary.totalGb)}
          </span>
          <Divider orientation="vertical" />
          {Object.entries(storageSummary.byType).map(([type, info]) => (
            <span key={type} style={{ marginRight: 20 }}>
              <Tag
                color={
                  type === 'SSD' ? 'blue' : type === 'NVME' || type === 'NVMe' ? 'green' : 'orange'
                }
              >
                {type}
              </Tag>
              {info.count}块 {formatGb(info.totalGb)}
            </span>
          ))}
        </div>
      )}

      <BatchActionBar count={batch.count} unit="条存储" onClear={batch.clear}>
        <Popconfirm title={`确定删除选中的 ${batch.count} 条存储？`} onConfirm={handleBatchDelete}>
          <Button danger icon={<DeleteOutlined />}>
            批量删除
          </Button>
        </Popconfirm>
      </BatchActionBar>

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
        dataSource={details}
        rowKey="id"
        loading={isLoading}
        size="small"
        scroll={{ x: 900 }}
        rowSelection={batch.rowSelection}
      />

      {}
      <Modal
        title="编辑存储"
        open={formOpen}
        onOk={handleSubmit}
        onCancel={() => setFormOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="storage_type"
            label="存储类型"
            rules={[{ required: true, message: '请选择存储类型' }]}
          >
            <Select
              placeholder="请选择"
              options={[
                { label: 'SSD', value: 'SSD' },
                { label: 'HDD', value: 'HDD' },
                { label: 'NVMe', value: 'NVMe' }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="capacity"
            label="容量"
            rules={[{ required: true, message: '请输入容量' }]}
          >
            <Input placeholder="如 2TB" />
          </Form.Item>
          <Form.Item name="capacity_gb" label="容量(GB)" extra="仅用于计算总容量，不会在列表中显示">
            <InputNumber min={1} style={{ width: '100%' }} placeholder="换算为GB，如 2TB填2048" />
          </Form.Item>
          <Form.Item name="interface_type" label="接口类型">
            <Select
              placeholder="请选择"
              options={[
                { label: 'SATA', value: 'SATA' },
                { label: 'SAS', value: 'SAS' },
                { label: 'NVMe', value: 'NVMe' }
              ]}
              allowClear
            />
          </Form.Item>
          <Form.Item name="slot_number" label="插槽号">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="插槽号" />
          </Form.Item>
          <Form.Item name="manufacturer" label="厂商">
            <Input placeholder="如 Samsung" />
          </Form.Item>
          <Form.Item name="model" label="型号">
            <Input placeholder="如 PM983" />
          </Form.Item>
          <Form.Item name="serial_number" label="序列号">
            <Input placeholder="序列号" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              placeholder="请选择"
              options={[
                { label: '正常', value: 'normal' },
                { label: '故障', value: 'fault' },
                { label: '预警', value: 'warning' }
              ]}
              allowClear
            />
          </Form.Item>
        </Form>
      </Modal>

      {}
      <Modal
        title="存储模板配置"
        open={templateOpen}
        onCancel={() => setTemplateOpen(false)}
        onOk={handleTemplateSubmit}
        okText="确认创建"
        confirmLoading={createStorage.isPending}
        width={700}
        destroyOnHidden
      >
        <Form form={templateForm} layout="vertical" autoComplete="off">
          <HardwareConfigFields form={templateForm} storageOnly />
        </Form>
      </Modal>
    </div>
  );
}

export default StorageTab;
