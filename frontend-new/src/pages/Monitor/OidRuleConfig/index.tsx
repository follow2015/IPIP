/**
 * OID 分类规则配置页
 *
 * 两个 Tab：
 * 1. 分类规则：OID 前缀 → category 映射（CRUD）
 * 2. 推荐配置：设备类型 → 推荐的 category 列表
 *
 * 厂商品牌管理已迁移至独立页面 /asset/vendor-brands（资产管理分组下）
 */
import { useState } from 'react';
import {
  Card,
  Tabs,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Tag,
  Typography,
  Checkbox,
  Row,
  Col
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import {
  useOidCategoryRules,
  useCreateOidCategoryRule,
  useUpdateOidCategoryRule,
  useDeleteOidCategoryRule,
  useDeviceTypeRecommends,
  useUpdateDeviceTypeRecommend,
  useVendorBrands,
  type OidCategoryRule
} from '@/services/monitor';

const { Text } = Typography;

const DEVICE_TYPE_OPTIONS = [
  { label: '全适用', value: '' },
  { label: 'network（网络设备）', value: 'network' },
  { label: 'server（服务器）', value: 'server' },
  { label: 'other（其他）', value: 'other' }
];

function useAllCategories(): string[] {
  const { data } = useOidCategoryRules();
  const set = new Set<string>();
  for (const r of data?.items ?? []) {
    set.add(r.category);
  }
  return Array.from(set).sort();
}

function CategoryRulesTab() {
  const { data, isLoading } = useOidCategoryRules();
  const { data: vendorBrands } = useVendorBrands();
  const createMut = useCreateOidCategoryRule();
  const updateMut = useUpdateOidCategoryRule();
  const deleteMut = useDeleteOidCategoryRule();
  const message = useMessage();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<OidCategoryRule | null>(null);
  const [form] = Form.useForm();
  const watchDeviceType = Form.useWatch('device_type', form) ?? '';
  const table = useTable({ initialPerPage: 50 });

  const watchVendorId = Form.useWatch('vendor_id', form) as string | undefined;
  const vendorOptions: { key: string | number; label: string; value: string }[] = (
    vendorBrands?.items ?? []
  )
    .filter((v) => v.enabled && (!watchDeviceType || v.device_type === watchDeviceType))
    .map((v) => ({ key: v.id, label: v.label, value: v.enterprise_no }));
  if (watchVendorId && !vendorOptions.some((o) => o.value === watchVendorId)) {
    vendorOptions.push({
      key: `__fallback__${watchVendorId}`,
      label: watchVendorId,
      value: watchVendorId
    });
  }

  const vendorLabelMap = new Map<string, string>();
  for (const v of vendorBrands?.items ?? []) {
    if (!vendorLabelMap.has(v.enterprise_no)) {
      vendorLabelMap.set(v.enterprise_no, v.label);
    }
  }
  const getVendorLabel = (vid: string | null | undefined) =>
    vid ? (vendorLabelMap.get(vid) ?? vid) : '通用';

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ priority: 10, enabled: true, device_type: '', vendor_id: '' });
    setModalOpen(true);
  };

  const openEdit = (rule: OidCategoryRule) => {
    setEditing(rule);
    form.setFieldsValue({
      ...rule,
      device_type: rule.device_type ?? '',
      vendor_id: rule.vendor_id ?? ''
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const payload = {
      ...values,
      device_type: values.device_type || null,
      vendor_id: values.vendor_id || null
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, ...payload });
        message.success('更新成功');
      } else {
        await createMut.mutateAsync(payload);
        message.success('新增成功');
      }
      setModalOpen(false);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success('删除成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const columns = [
    {
      title: 'OID 前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      width: 320,
      render: (v: string) => (
        <Text code style={{ fontSize: 12 }}>
          {v}
        </Text>
      )
    },
    {
      title: 'category',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '标签',
      dataIndex: 'label',
      key: 'label',
      width: 120,
      render: (v: string) => v ?? '-'
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (v: string) => (v ? <Tag>{v}</Tag> : <Text type="secondary">全适用</Text>)
    },
    {
      title: '厂商',
      dataIndex: 'vendor_id',
      key: 'vendor_id',
      width: 120,
      render: (v: string) =>
        v ? <Tag color="blue">{getVendorLabel(v)}</Tag> : <Text type="secondary">通用</Text>
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 60,
      render: (v: boolean) => <Switch checked={v} disabled size="small" />
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, r: OidCategoryRule) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <ConfirmButton
            type="link"
            size="small"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该分类规则吗？此操作不可恢复。"
            onConfirm={() => handleDelete(r.id)}
          >
            {null}
          </ConfirmButton>
        </Space>
      )
    }
  ];

  return (
    <Card
      title="OID 分类规则"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增规则
        </Button>
      }
    >
      <DataTable<OidCategoryRule>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => String(r.id)}
        total={data?.items?.length ?? 0}
        emptyText="暂无分类规则"
        searchable={false}
        showCard={false}
        tableProps={table}
      />
      <Modal
        title={editing ? '编辑规则' : '新增规则'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="prefix"
            label="OID 前缀"
            rules={[{ required: true, message: '请输入 OID 前缀' }]}
          >
            <Input placeholder="1.3.6.1.4.1.674.10892.5.4.300" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="category"
                label="category"
                rules={[{ required: true, message: '请输入 category' }]}
              >
                <Input placeholder="temperature" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="label" label="标签">
                <Input placeholder="温度探头" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="device_type" label="设备类型">
                <Select options={DEVICE_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="vendor_id" label="厂商">
                <Select
                  options={vendorOptions ?? []}
                  showSearch
                  allowClear
                  placeholder="选择厂商或留空通用"
                  filterOption={(input, option) =>
                    (option?.label as string).toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="priority" label="优先级">
                <InputNumber min={0} max={999} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function RecommendConfigTab() {
  const { data, isLoading } = useDeviceTypeRecommends();
  const updateMut = useUpdateDeviceTypeRecommend();
  const message = useMessage();
  const allCategories = useAllCategories();
  const [editingType, setEditingType] = useState<string | null>(null);
  const [selectedCats, setSelectedCats] = useState<string[]>([]);

  const openEdit = (deviceType: string, cats: string[]) => {
    setEditingType(deviceType);
    setSelectedCats(cats);
  };

  const handleSave = async () => {
    if (!editingType) return;
    try {
      await updateMut.mutateAsync({ device_type: editingType, categories: selectedCats });
      message.success('更新成功');
      setEditingType(null);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  };

  const columns = [
    {
      title: '设备类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 120,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '推荐 category 列表',
      dataIndex: 'categories',
      key: 'categories',
      render: (cats: string[]) => (
        <Space wrap>
          {cats.map((c) => (
            <Tag key={c}>{c}</Tag>
          ))}
        </Space>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, r: { device_type: string; categories: string[] }) => (
        <Button
          type="link"
          size="small"
          icon={<EditOutlined />}
          onClick={() => openEdit(r.device_type, r.categories)}
        >
          编辑
        </Button>
      )
    }
  ];

  return (
    <Card title="设备类型推荐配置">
      <Table
        rowKey="device_type"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        pagination={false}
        size="small"
      />
      <Modal
        title={`编辑推荐配置：${editingType}`}
        open={!!editingType}
        onOk={handleSave}
        onCancel={() => setEditingType(null)}
        confirmLoading={updateMut.isPending}
        width={600}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          勾选该设备类型探测后"推荐勾选"按钮会自动选中的 category
        </Text>
        <Checkbox.Group
          value={selectedCats}
          onChange={(vals) => setSelectedCats(vals as string[])}
          style={{ width: '100%' }}
        >
          <Row>
            {allCategories.map((c) => (
              <Col span={8} key={c}>
                <Checkbox value={c}>{c}</Checkbox>
              </Col>
            ))}
          </Row>
        </Checkbox.Group>
      </Modal>
    </Card>
  );
}

export default function OidRuleConfigPage() {
  return (
    <Card variant="borderless">
      <Tabs
        defaultActiveKey="rules"
        items={[
          { key: 'rules', label: '分类规则', children: <CategoryRulesTab /> },
          { key: 'recommend', label: '推荐配置', children: <RecommendConfigTab /> }
        ]}
      />
    </Card>
  );
}
