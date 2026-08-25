/**
 * 厂商品牌管理页（独立页面，原为 OID 规则配置的 Tab 之一）
 * 后端 API 路径不变：/monitor/vendor-brands
 */
import { useState } from 'react';
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
import {
  useVendorBrands,
  useCreateVendorBrand,
  useUpdateVendorBrand,
  useDeleteVendorBrand,
  type VendorBrand
} from '@/services/monitor';

const { Text } = Typography;

export default function VendorBrandsPage() {
  const { data, isLoading } = useVendorBrands();
  const createMut = useCreateVendorBrand();
  const updateMut = useUpdateVendorBrand();
  const deleteMut = useDeleteVendorBrand();
  const message = useMessage();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VendorBrand | null>(null);
  const [form] = Form.useForm();
  const table = useTable({ initialPerPage: 50 });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, sort_order: 0, device_type: 'server' });
    setModalOpen(true);
  };

  const openEdit = (brand: VendorBrand) => {
    setEditing(brand);
    form.setFieldsValue(brand);
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createMut.mutateAsync(values);
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
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60
    },
    {
      title: 'enterprise 号',
      dataIndex: 'enterprise_no',
      key: 'enterprise_no',
      width: 120,
      render: (v: string) => <Text code>{v}</Text>
    },
    {
      title: '品牌全称',
      dataIndex: 'brand_name',
      key: 'brand_name',
      width: 160
    },
    {
      title: '显示名称',
      dataIndex: 'label',
      key: 'label',
      width: 180,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>
    },
    {
      title: '排序',
      dataIndex: 'sort_order',
      key: 'sort_order',
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
      render: (_: unknown, r: VendorBrand) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <ConfirmButton
            type="link"
            size="small"
            icon={<DeleteOutlined />}
            title="确认删除"
            content="确定要删除该厂商品牌吗？此操作不可恢复。"
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
      title="厂商品牌"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增品牌
        </Button>
      }
    >
      <DataTable<VendorBrand>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => String(r.id)}
        total={data?.items?.length ?? 0}
        emptyText="暂无厂商品牌"
        searchable={false}
        showCard={false}
        tableProps={table}
      />
      <Modal
        title={editing ? '编辑品牌' : '新增品牌'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="enterprise_no"
                label="enterprise 号"
                rules={[{ required: true, message: '请输入 enterprise 号' }]}
              >
                <Input placeholder="674" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="device_type"
                label="设备类型"
                rules={[{ required: true, message: '请选择设备类型' }]}
              >
                <Select
                  options={[
                    { label: 'network（网络）', value: 'network' },
                    { label: 'server（服务器）', value: 'server' },
                    { label: 'storage（存储）', value: 'storage' },
                    { label: 'other（其他）', value: 'other' }
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="brand_name"
                label="品牌全称"
                rules={[{ required: true, message: '请输入品牌全称' }]}
              >
                <Input placeholder="Dell EMC" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="label"
                label="显示名称"
                rules={[{ required: true, message: '请输入显示名称' }]}
              >
                <Input placeholder="DELL（服务器）" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="sort_order" label="排序">
                <InputNumber min={0} max={999} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Card>
  );
}
