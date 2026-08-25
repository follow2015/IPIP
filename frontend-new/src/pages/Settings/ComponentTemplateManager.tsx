/**
 * 配件模板管理页面
 * - 客户筛选 + 类别 Tabs (CPU | 内存 | 硬盘 | 网卡)
 * - Table 展示：客户归属、品牌、型号、规格摘要、启用、排序、操作
 * - TemplateFormModal：新增/编辑，含客户归属 Select + 四类 spec 字段
 */
import { useState, useMemo } from 'react';
import {
  Tabs,
  Table,
  Modal,
  Form,
  Select,
  Input,
  InputNumber,
  Tag,
  Button,
  Space,
  Popconfirm,
  Switch
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  useComponentTemplates,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate
} from '@/services/component-template';
import type { ComponentTemplate } from '@/services/component-template';
import { useCustomerOptions, useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';
import FilterBar from '@/components/FilterBar';
import IdCell from '@/components/IdCell';
import { useTable } from '@/hooks/useTable';
import {
  CpuSpecFields,
  MemorySpecFields,
  DiskSpecFields,
  NicSpecFields,
  GpuSpecFields
} from './ComponentSpecFields';

const CATEGORY_LABELS: Record<string, string> = {
  cpu: 'CPU',
  memory: '内存',
  disk: '硬盘',
  nic: '网卡',
  gpu: '显卡'
};

const CATEGORY_OPTIONS = [
  { label: 'CPU', key: 'cpu' },
  { label: '内存', key: 'memory' },
  { label: '硬盘', key: 'disk' },
  { label: '网卡', key: 'nic' },
  { label: '显卡', key: 'gpu' }
];

function specSummary(category: string, spec: Record<string, unknown>): string {
  if (!spec || typeof spec !== 'object') return '-';
  const parts: string[] = [];
  switch (category) {
    case 'cpu':
      if (spec.cores_per_cpu) parts.push(`${spec.cores_per_cpu}核`);
      if (spec.architecture) parts.push(String(spec.architecture));
      if (spec.base_freq_ghz) parts.push(`${spec.base_freq_ghz}GHz`);
      break;
    case 'memory':
      if (spec.capacity_gb) parts.push(`${spec.capacity_gb}GB`);
      if (spec.type) parts.push(String(spec.type));
      if (spec.speed_mhz) parts.push(`${spec.speed_mhz}MHz`);
      break;
    case 'disk':
      if (spec.storage_type) parts.push(String(spec.storage_type));
      if (spec.capacity_gb) parts.push(`${spec.capacity_gb}GB`);
      if (spec.interface_type) parts.push(String(spec.interface_type));
      break;
    case 'nic':
      if (spec.port_count) parts.push(`${spec.port_count}口`);
      if (spec.port_speed) parts.push(String(spec.port_speed));
      if (spec.port_type) parts.push(String(spec.port_type));
      break;
    case 'gpu':
      if (spec.vram_gb) parts.push(`${spec.vram_gb}GB`);
      if (spec.gpu_memory_type) parts.push(String(spec.gpu_memory_type));
      if (spec.fp32_tflops) parts.push(`${spec.fp32_tflops}TFLOPS`);
      break;
  }
  return parts.length > 0 ? parts.join(' / ') : '-';
}

interface TemplateFormValues {
  category: 'cpu' | 'memory' | 'disk' | 'nic' | 'gpu';
  customer_id: number | null;
  brand: string;
  model: string;
  spec: Record<string, string | number | boolean | null>;
  is_active: boolean;
  sort_order: number;
  remark: string;
}

function ComponentTemplateManager() {
  const message = useMessage();
  const [form] = Form.useForm<TemplateFormValues>();

  const [activeCategory, setActiveCategory] = useState<string>('cpu');
  const filterTable = useTable();

  const [modalOpen, setModalOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<ComponentTemplate | null>(null);

  const { data: templates, isLoading } = useComponentTemplates(
    activeCategory,
    filterTable.filters.customer_id ? Number(filterTable.filters.customer_id) : null,
    false
  );
  const { data: customerOptions } = useCustomerOptions();
  const { data: allocatableCustomerOptions } = useAllocatableCustomerOptions();
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const deleteTemplate = useDeleteTemplate();

  const customerSelectOptions = useMemo(
    () => (customerOptions ?? []).map((o) => ({ label: o.label, value: o.value as number })),
    [customerOptions]
  );

  const allocatableCustomerSelectOptions = useMemo(
    () =>
      (allocatableCustomerOptions ?? []).map((o) => ({ label: o.label, value: o.value as number })),
    [allocatableCustomerOptions]
  );

  const handleAdd = () => {
    setEditRecord(null);
    form.resetFields();
    form.setFieldsValue({
      category: activeCategory as TemplateFormValues['category'],
      customer_id: null,
      brand: '',
      model: '',
      spec: {},
      is_active: true,
      sort_order: 0,
      remark: ''
    });
    setModalOpen(true);
  };

  const handleEdit = (record: ComponentTemplate) => {
    setEditRecord(record);
    form.setFieldsValue({
      category: record.category,
      customer_id: record.customer_id,
      brand: record.brand,
      model: record.model,
      spec: record.spec as Record<string, string | number | boolean | null>,
      is_active: record.is_active,
      sort_order: record.sort_order,
      remark: record.remark
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteTemplate.mutateAsync(id);
      message.success('删除成功');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleFormSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editRecord) {
        await updateTemplate.mutateAsync({ id: editRecord.id, data: values });
        message.success('更新成功');
      } else {
        await createTemplate.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  const modalCategory = Form.useWatch('category', form) ?? activeCategory;

  const columns: ColumnsType<ComponentTemplate> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    {
      title: '客户归属',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) => (v ? <Tag>{v}</Tag> : <Tag color="default">通用</Tag>)
    },
    { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
    { title: '型号', dataIndex: 'model', key: 'model', width: 160 },
    {
      title: '规格摘要',
      key: 'spec_summary',
      width: 200,
      render: (_: unknown, r: ComponentTemplate) => specSummary(r.category, r.spec)
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 60,
      render: (v: boolean) => (v ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>)
    },
    { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 60 },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 150,
      ellipsis: true,
      render: (v: string | null) => v || '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, r: ComponentTemplate) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            编辑
          </Button>
          <Popconfirm
            title={`确定要删除「${r.brand} ${r.model}」吗？`}
            onConfirm={() => handleDelete(r.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* 顶部筛选栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <FilterBar
          filters={[
            {
              key: 'customer_id',
              label: '筛选客户',
              type: 'select',
              options: customerSelectOptions,
              width: 200
            }
          ]}
          table={filterTable}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增模板
        </Button>
      </div>

      {/* 类别 Tabs + Table */}
      <Tabs
        activeKey={activeCategory}
        onChange={(key) => setActiveCategory(key)}
        items={CATEGORY_OPTIONS.map((cat) => ({
          key: cat.key,
          label: cat.label,
          children: (
            <Table<ComponentTemplate>
              columns={columns}
              dataSource={templates ?? []}
              loading={isLoading}
              rowKey="id"
              size="middle"
              pagination={{ pageSize: 20, showSizeChanger: true }}
            />
          )
        }))}
      />

      {/* 新增/编辑弹窗 */}
      <Modal
        title={editRecord ? '编辑配件模板' : '新增配件模板'}
        open={modalOpen}
        onOk={handleFormSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createTemplate.isPending || updateTemplate.isPending}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select
              options={CATEGORY_OPTIONS.map((c) => ({ label: c.label, value: c.key }))}
              disabled={!!editRecord}
            />
          </Form.Item>
          <Form.Item name="customer_id" label="客户归属">
            <Select
              placeholder="通用（不选客户）"
              allowClear
              options={allocatableCustomerSelectOptions}
            />
          </Form.Item>
          <Form.Item name="brand" label="品牌" rules={[{ required: true, message: '请输入品牌' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model" label="型号" rules={[{ required: true, message: '请输入型号' }]}>
            <Input />
          </Form.Item>

          {/* 动态 spec 字段 */}
          {modalCategory === 'cpu' && <CpuSpecFields prefix={['spec']} />}
          {modalCategory === 'memory' && <MemorySpecFields prefix={['spec']} />}
          {modalCategory === 'disk' && <DiskSpecFields prefix={['spec']} />}
          {modalCategory === 'nic' && <NicSpecFields prefix={['spec']} />}
          {modalCategory === 'gpu' && <GpuSpecFields prefix={['spec']} />}

          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={0} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default ComponentTemplateManager;
