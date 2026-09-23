/**
 * 厂商品牌管理页（独立页面，原为 OID 规则配置的 Tab 之一）
 * 后端 API 路径不变：/monitor/vendor-brands
 */
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
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
  Row,
  Col
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useTranslation } from 'react-i18next';
import {
  useVendorBrands,
  useCreateVendorBrand,
  useUpdateVendorBrand,
  useDeleteVendorBrand,
  type VendorBrand
} from '@/services/monitor';

const { Text } = Typography;

export default function VendorBrandsPage() {
  const { t: ta } = useTranslation('asset');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const { data, isLoading } = useVendorBrands();
  const createMut = useCreateVendorBrand();
  const updateMut = useUpdateVendorBrand();
  const deleteMut = useDeleteVendorBrand();
  const message = useMessage();
  const modal = useDisclosure();
  const [editing, setEditing] = useState<VendorBrand | null>(null);
  const [form] = Form.useForm();
  const table = useTable({ initialPerPage: 50 });


  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, sort_order: 0, device_type: 'server' });
    modal.open();
  };

  const openEdit = (brand: VendorBrand) => {
    setEditing(brand);
    form.setFieldsValue(brand);
    modal.open();
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, ...values });
        message.success(tc('message.updateSuccess'));
      } else {
        await createMut.mutateAsync(values);
        message.success(ta('vendorBrand.message.created'));
      }
      modal.close();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : ta('vendorBrand.message.saveFailed'));
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
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60
    },
    {
      title: ta('vendorBrand.field.enterpriseNo'),
      dataIndex: 'enterprise_no',
      key: 'enterprise_no',
      width: 120,
      render: (v: string) => <Text code>{v}</Text>
    },
    {
      title: ta('vendorBrand.field.brandName'),
      dataIndex: 'brand_name',
      key: 'brand_name',
      width: 160
    },
    {
      title: ta('vendorBrand.field.displayName'),
      dataIndex: 'label',
      key: 'label',
      width: 180,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: td('basic.field.deviceType'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>
    },
    {
      title: ta('vendorBrand.field.sortOrder'),
      dataIndex: 'sort_order',
      key: 'sort_order',
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
      render: (_: unknown, r: VendorBrand) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <ConfirmButton
            type="link"
            size="small"
            icon={<DeleteOutlined />}
            title={tc('confirm.deleteTitle')}
            content={ta('vendorBrand.confirmDeleteContent')}
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
      title={ta('vendorBrand.title')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {ta('vendorBrand.add')}
        </Button>
      }
    >
      <DataTable<VendorBrand>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => String(r.id)}
        total={data?.items?.length ?? 0}
        emptyText={ta('vendorBrand.empty')}
        searchable={false}
        showCard={false}
        tableProps={table}
      />
      <Modal
        title={editing ? ta('vendorBrand.edit') : ta('vendorBrand.add')}
        open={modal.isOpen}
        onOk={handleSave}
        onCancel={() => modal.close()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="enterprise_no"
                label={ta('vendorBrand.field.enterpriseNo')}
                rules={[
                  { required: true, message: ta('vendorBrand.validation.enterpriseNoRequired') }
                ]}
              >
                <Input placeholder="674" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="device_type"
                label={td('basic.field.deviceType')}
                rules={[
                  { required: true, message: ta('vendorBrand.validation.deviceTypeRequired') }
                ]}
              >
                <Select
                  options={[
                    { label: ta('vendorBrand.deviceType.network'), value: 'network' },
                    { label: ta('vendorBrand.deviceType.server'), value: 'server' },
                    { label: ta('vendorBrand.deviceType.storage'), value: 'storage' },
                    { label: ta('vendorBrand.deviceType.other'), value: 'other' }
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="brand_name"
                label={ta('vendorBrand.field.brandName')}
                rules={[{ required: true, message: ta('vendorBrand.validation.brandNameRequired') }]}
              >
                <Input placeholder="Dell EMC" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="label"
                label={ta('vendorBrand.field.displayName')}
                rules={[
                  { required: true, message: ta('vendorBrand.validation.displayNameRequired') }
                ]}
              >
                <Input placeholder={ta('vendorBrand.field.labelPlaceholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="sort_order" label={ta('vendorBrand.field.sortOrder')}>
                <InputNumber min={0} max={999} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Card>
  );
}
