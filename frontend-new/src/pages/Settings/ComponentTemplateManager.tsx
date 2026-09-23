/**
 * 配件模板管理页面
 * - 客户筛选 + 类别 Tabs (CPU | 内存 | 硬盘 | 网卡)
 * - Table 展示：客户归属、品牌、型号、规格摘要、启用、排序、操作
 * - TemplateFormModal：新增/编辑，含客户归属 Select + 四类 spec 字段
 */
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Tabs, Modal, Form, Select, Input, InputNumber, Tag, Button, Space, Switch } from 'antd';
import DataTable from '@/components/DataTable';
import { useConfirm } from '@/utils/confirm';
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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
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

type CategoryKey = 'cpu' | 'memory' | 'disk' | 'nic' | 'gpu';

type SettingsT = TFunction<'settings'>;

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  cpu: 'componentTemplate.category.cpu',
  memory: 'componentTemplate.category.memory',
  disk: 'componentTemplate.category.disk',
  nic: 'componentTemplate.category.nic',
  gpu: 'componentTemplate.category.gpu'
};

const CATEGORY_KEYS: CategoryKey[] = ['cpu', 'memory', 'disk', 'nic', 'gpu'];

function specSummary(
  t: SettingsT,
  category: string,
  spec: Record<string, unknown>
): string {
  if (!spec || typeof spec !== 'object') return '-';
  const parts: string[] = [];
  switch (category) {
    case 'cpu':
      if (spec.cores_per_cpu)
        parts.push(t('componentTemplate.spec.cores', { value: String(spec.cores_per_cpu) }));
      if (spec.architecture) parts.push(String(spec.architecture));
      if (spec.base_freq_ghz)
        parts.push(t('componentTemplate.spec.freq', { value: String(spec.base_freq_ghz) }));
      break;
    case 'memory':
      if (spec.capacity_gb)
        parts.push(t('componentTemplate.spec.capacity', { value: String(spec.capacity_gb) }));
      if (spec.type) parts.push(String(spec.type));
      if (spec.speed_mhz)
        parts.push(t('componentTemplate.spec.speed', { value: String(spec.speed_mhz) }));
      break;
    case 'disk':
      if (spec.storage_type) parts.push(String(spec.storage_type));
      if (spec.capacity_gb)
        parts.push(t('componentTemplate.spec.capacity', { value: String(spec.capacity_gb) }));
      if (spec.interface_type) parts.push(String(spec.interface_type));
      break;
    case 'nic':
      if (spec.port_count)
        parts.push(t('componentTemplate.spec.ports', { value: String(spec.port_count) }));
      if (spec.port_speed) parts.push(String(spec.port_speed));
      if (spec.port_type) parts.push(String(spec.port_type));
      break;
    case 'gpu':
      if (spec.vram_gb)
        parts.push(t('componentTemplate.spec.capacity', { value: String(spec.vram_gb) }));
      if (spec.gpu_memory_type) parts.push(String(spec.gpu_memory_type));
      if (spec.fp32_tflops)
        parts.push(t('componentTemplate.spec.tflops', { value: String(spec.fp32_tflops) }));
      break;
  }
  return parts.length > 0 ? parts.join(t('componentTemplate.spec.separator')) : '-';
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
  const confirm = useConfirm();
  const message = useMessage();
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [form] = Form.useForm<TemplateFormValues>();

  const [activeCategory, setActiveCategory] = useState<string>('cpu');
  const filterTable = useTable();

  const modal = useDisclosure();
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

  const categoryOptions = useMemo(
    () => CATEGORY_KEYS.map((key) => ({ key, label: t(`componentTemplate.category.${key}`) })),
    [t]
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
    modal.open();
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
    modal.open();
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteTemplate.mutateAsync(id);
      message.success(tc('message.deleteSuccess'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const handleFormSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editRecord) {
        await updateTemplate.mutateAsync({ id: editRecord.id, data: values });
        message.success(tc('message.updateSuccess'));
      } else {
        await createTemplate.mutateAsync(values);
        message.success(tc('message.createSuccess'));
      }
      modal.close();
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
      title: t('componentTemplate.column.customerOwner'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) =>
        v ? <Tag>{v}</Tag> : <Tag color="default">{t('componentTemplate.shared')}</Tag>
    },
    {
      title: t('componentTemplate.column.brand'),
      dataIndex: 'brand',
      key: 'brand',
      width: 100
    },
    {
      title: t('componentTemplate.column.model'),
      dataIndex: 'model',
      key: 'model',
      width: 160
    },
    {
      title: t('componentTemplate.column.specSummary'),
      key: 'spec_summary',
      width: 200,
      render: (_: unknown, r: ComponentTemplate) => specSummary(t, r.category, r.spec)
    },
    {
      title: t('componentTemplate.column.enabled'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 60,
      render: (v: boolean) =>
        v ? <Tag color="green">{t('componentTemplate.yes')}</Tag> : <Tag color="red">{t('componentTemplate.no')}</Tag>
    },
    {
      title: t('componentTemplate.column.sortOrder'),
      dataIndex: 'sort_order',
      key: 'sort_order',
      width: 60
    },
    {
      title: tc('field.remarks'),
      dataIndex: 'remark',
      key: 'remark',
      width: 150,
      ellipsis: true,
      render: (v: string | null) => v || '-'
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 140,
      render: (_: unknown, r: ComponentTemplate) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            {tc('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              confirm({
                title: t('componentTemplate.deleteConfirmTitle', {
                  name: `${r.brand} ${r.model}`
                }),
                okText: tc('action.delete'),
                okButtonProps: { danger: true },
                onOk: () => handleDelete(r.id)
              })
            }
          >
            {tc('action.delete')}
          </Button>
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
              label: t('componentTemplate.filterCustomer'),
              type: 'select',
              options: customerSelectOptions,
              width: 200
            }
          ]}
          table={filterTable}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          {t('componentTemplate.addTemplate')}
        </Button>
      </div>

      {/* 类别 Tabs + Table */}
      <Tabs
        activeKey={activeCategory}
        onChange={(key) => setActiveCategory(key)}
        items={categoryOptions.map((cat) => ({
          key: cat.key,
          label: cat.label,
          children: (
            <DataTable<ComponentTemplate>
              columns={columns}
              dataSource={templates ?? []}
              loading={isLoading}
              rowKey="id"
              size="middle"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 'max-content' }}
              showCard={false}
              searchable={false}
            />
          )
        }))}
      />

      {/* 新增/编辑弹窗 */}
      <Modal
        title={
          editRecord ? t('componentTemplate.modal.editTitle') : t('componentTemplate.modal.createTitle')
        }
        open={modal.isOpen}
        onOk={handleFormSubmit}
        onCancel={() => modal.close()}
        confirmLoading={createTemplate.isPending || updateTemplate.isPending}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="category"
            label={t('componentTemplate.field.category')}
            rules={[{ required: true }]}
          >
            <Select
              options={categoryOptions.map((c) => ({ label: c.label, value: c.key }))}
              disabled={!!editRecord}
            />
          </Form.Item>
          <Form.Item name="customer_id" label={t('componentTemplate.column.customerOwner')}>
            <Select
              placeholder={t('componentTemplate.placeholder.customerOwner')}
              allowClear
              options={allocatableCustomerSelectOptions}
            />
          </Form.Item>
          <Form.Item
            name="brand"
            label={t('componentTemplate.column.brand')}
            rules={[{ required: true, message: t('componentTemplate.validation.brandRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="model"
            label={t('componentTemplate.column.model')}
            rules={[{ required: true, message: t('componentTemplate.validation.modelRequired') }]}
          >
            <Input />
          </Form.Item>

          {/* 动态 spec 字段 */}
          {modalCategory === 'cpu' && <CpuSpecFields prefix={['spec']} />}
          {modalCategory === 'memory' && <MemorySpecFields prefix={['spec']} />}
          {modalCategory === 'disk' && <DiskSpecFields prefix={['spec']} />}
          {modalCategory === 'nic' && <NicSpecFields prefix={['spec']} />}
          {modalCategory === 'gpu' && <GpuSpecFields prefix={['spec']} />}

          <Form.Item
            name="is_active"
            label={t('componentTemplate.column.enabled')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item name="sort_order" label={t('componentTemplate.column.sortOrder')}>
            <InputNumber min={0} />
          </Form.Item>
          <Form.Item name="remark" label={tc('field.remarks')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default ComponentTemplateManager;
