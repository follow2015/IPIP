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
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Tabs,
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
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

function useAllCategories(): string[] {
  const { data } = useOidCategoryRules();
  const set = new Set<string>();
  for (const r of data?.items ?? []) {
    set.add(r.category);
  }
  return Array.from(set).sort();
}

function CategoryRulesTab() {
  const { t } = useTranslation('monitor');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { data, isLoading } = useOidCategoryRules();
  const { data: vendorBrands } = useVendorBrands();
  const createMut = useCreateOidCategoryRule();
  const updateMut = useUpdateOidCategoryRule();
  const deleteMut = useDeleteOidCategoryRule();
  const message = useMessage();
  const modal = useDisclosure();
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
    vid ? (vendorLabelMap.get(vid) ?? vid) : t('oid.vendor.generic');

  const deviceTypeOptions = [
    { label: t('oid.deviceType.all'), value: '' },
    { label: t('oid.deviceType.network'), value: 'network' },
    { label: t('oid.deviceType.server'), value: 'server' },
    { label: t('oid.deviceType.other'), value: 'other' }
  ];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ priority: 10, enabled: true, device_type: '', vendor_id: '' });
    modal.open();
  };

  const openEdit = (rule: OidCategoryRule) => {
    setEditing(rule);
    form.setFieldsValue({
      ...rule,
      device_type: rule.device_type ?? '',
      vendor_id: rule.vendor_id ?? ''
    });
    modal.open();
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
        message.success(tc('message.updateSuccess'));
      } else {
        await createMut.mutateAsync(payload);
        message.success(tc('message.createSuccess'));
      }
      modal.close();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('oid.rule.message.saveFailed'));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id);
      message.success(tc('message.deleteSuccess'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const columns = [
    {
      title: t('oid.rule.field.oidPrefix'),
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
      title: t('oid.rule.field.label'),
      dataIndex: 'label',
      key: 'label',
      width: 120,
      render: (v: string) => v ?? '-'
    },
    {
      title: td('switch.batchField.deviceType'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (v: string) =>
        v ? <Tag>{v}</Tag> : <Text type="secondary">{t('oid.deviceType.all')}</Text>
    },
    {
      title: t('metricTemplate.field.vendor'),
      dataIndex: 'vendor_id',
      key: 'vendor_id',
      width: 120,
      render: (v: string) =>
        v ? (
          <Tag color="blue">{getVendorLabel(v)}</Tag>
        ) : (
          <Text type="secondary">{t('oid.vendor.generic')}</Text>
        )
    },
    {
      title: t('oid.rule.field.priority'),
      dataIndex: 'priority',
      key: 'priority',
      width: 80
    },
    {
      title: tc('action.enable'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 60,
      render: (v: boolean) => <Switch checked={v} disabled size="small" />
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 120,
      render: (_: unknown, r: OidCategoryRule) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <ConfirmButton
            type="link"
            size="small"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={t('oid.rule.confirm.deleteContent')}
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
      title={t('oid.rule.title')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t('oid.rule.action.create')}
        </Button>
      }
    >
      <DataTable<OidCategoryRule>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => String(r.id)}
        total={data?.items?.length ?? 0}
        emptyText={t('oid.rule.empty')}
        searchable={false}
        showCard={false}
        tableProps={table}
      />
      <Modal
        title={editing ? t('oid.rule.modal.editTitle') : t('oid.rule.modal.createTitle')}
        open={modal.isOpen}
        onOk={handleSave}
        onCancel={() => modal.close()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="prefix"
            label={t('oid.rule.field.oidPrefix')}
            rules={[{ required: true, message: t('oid.rule.validation.prefixRequired') }]}
          >
            <Input placeholder="1.3.6.1.4.1.674.10892.5.4.300" />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="category"
                label="category"
                rules={[{ required: true, message: t('oid.rule.validation.categoryRequired') }]}
              >
                <Input placeholder="temperature" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="label" label={t('oid.rule.field.label')}>
                <Input placeholder={t('oid.rule.placeholder.label')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="device_type" label={td('switch.batchField.deviceType')}>
                <Select options={deviceTypeOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="vendor_id" label={t('metricTemplate.field.vendor')}>
                <Select
                  options={vendorOptions ?? []}
                  showSearch
                  allowClear
                  placeholder={t('oid.rule.placeholder.vendor')}
                  filterOption={(input, option) =>
                    (option?.label as string).toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="priority" label={t('oid.rule.field.priority')}>
                <InputNumber min={0} max={999} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function RecommendConfigTab() {
  const { t } = useTranslation('monitor');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
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
      message.success(tc('message.updateSuccess'));
      setEditingType(null);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('oid.rule.message.saveFailed'));
    }
  };

  const columns = [
    {
      title: td('switch.batchField.deviceType'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 120,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: t('oid.recommend.column.categories'),
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
      title: tc('field.actions'),
      key: 'action',
      width: 80,
      render: (_: unknown, r: { device_type: string; categories: string[] }) => (
        <Button
          type="link"
          size="small"
          icon={<EditOutlined />}
          onClick={() => openEdit(r.device_type, r.categories)}
        >
          {tc('action.edit')}
        </Button>
      )
    }
  ];

  return (
    <Card title={t('oid.recommend.title')}>
      <DataTable
        rowKey="device_type"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        pagination={false}
        size="small"
        searchable={false}
        showCard={false}
      />
      <Modal
        title={t('oid.recommend.modal.editTitle', { type: editingType })}
        open={!!editingType}
        onOk={handleSave}
        onCancel={() => setEditingType(null)}
        confirmLoading={updateMut.isPending}
        width={600}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          {t('oid.recommend.hint')}
        </Text>
        <Checkbox.Group
          value={selectedCats}
          onChange={(vals) => setSelectedCats(vals as string[])}
          style={{ width: '100%' }}
        >
          <Row>
            {allCategories.map((c) => (
              <Col xs={24} md={8} key={c}>
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
  const { t } = useTranslation('monitor');
  return (
    <Card variant="borderless">
      <Tabs
        defaultActiveKey="rules"
        items={[
          { key: 'rules', label: t('oid.tab.rules'), children: <CategoryRulesTab /> },
          { key: 'recommend', label: t('oid.tab.recommend'), children: <RecommendConfigTab /> }
        ]}
      />
    </Card>
  );
}
