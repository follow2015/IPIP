/**
 * 客户管理页面
 * - 列表展示所有字段（名称、状态、联系人、电话、邮箱、地址、更新时间）
 * - 支持新增/编辑/删除
 * - "资源"按钮跳转到客户详情页
 * - 状态数字映射为文本 Tag
 *
 * 列表页骨架（分页/搜索/表单开关/删除确认）由 useCrudPage 统一提供，
 * 本页面仅保留资源跳转、表单提交等特有逻辑。
 */
import { Button, Space, Tag, message, Modal, Input } from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  BarChartOutlined,
  CopyOutlined,
  StopOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import DataTable from '@/components/DataTable';
import IdCell from '@/components/IdCell';
import CustomerForm from './CustomerForm';
import { useCustomerList, useDeleteCustomer, useTerminateCustomer } from '@/services/customer';
import type { Customer } from '@/types/models';
import { CUSTOMER_STATUS_MAP, CustomerStatusCode } from '@/types/enums';
import { useCrudPage } from '@/hooks/useCrudPage';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';

function renderStatus(v: number) {
  const s = CUSTOMER_STATUS_MAP[v as keyof typeof CUSTOMER_STATUS_MAP];
  if (v === undefined || v === null) return '-';
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}

function customerStatusLabel(v: number | null | undefined) {
  if (v === null || v === undefined) return '-';
  const s = CUSTOMER_STATUS_MAP[v as keyof typeof CUSTOMER_STATUS_MAP];
  return s ? s.label : String(v);
}

function buildCustomerInfoText(c: Customer): string {
  return [
    '客户信息',
    `ID: ${c.id}`,
    `客户名称: ${c.customer_name ?? '-'}`,
    `状态: ${customerStatusLabel(c.customer_status)}`,
    `联系人: ${c.contact_person ?? '-'}`,
    `联系电话: ${c.contact_phone ?? '-'}`,
    `邮箱: ${c.email ?? '-'}`,
    `地址: ${c.address ?? '-'}`
  ].join('\n');
}

function Customers() {
  const navigate = useNavigate();
  const message = useMessage();

  const crud = useCrudPage<Customer>({
    useList: useCustomerList,
    useDelete: useDeleteCustomer,
    nameKey: 'customer_name',
    nameLabel: '客户'
  });

  const { table, data, isLoading, refetch } = crud;

  const [terminateTarget, setTerminateTarget] = useState<Customer | null>(null);
  const [terminateReason, setTerminateReason] = useState('');
  const terminateMutation = useTerminateCustomer();

  const handleAssets = (r: Customer) => {
    navigate(`/customers/${r.id}`);
  };

  const handleCopy = (r: Customer) => {
    const text = buildCustomerInfoText(r);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => message.success('客户信息已复制'))
        .catch(() => message.error('复制失败，请手动复制'));
    } else {
      message.error('当前环境不支持自动复制');
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    { title: '客户名称', dataIndex: 'customer_name', key: 'customer_name', width: 160 },
    {
      title: '状态',
      dataIndex: 'customer_status',
      key: 'customer_status',
      width: 80,
      render: renderStatus
    },
    {
      title: '联系人',
      dataIndex: 'contact_person',
      key: 'contact_person',
      width: 100,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '联系电话',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      width: 130,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 180,
      render: (v: string | null) => v ?? '-',
      ellipsis: true
    },
    {
      title: '地址',
      dataIndex: 'address',
      key: 'address',
      width: 200,
      render: (v: string | null) => v ?? '-',
      ellipsis: true
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: '操作',
      key: 'action',
      width: 240,
      render: (_: unknown, r: Customer) => (
        <Space>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(r)}>
            复制
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => crud.handleEdit(r)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<BarChartOutlined />}
            onClick={() => handleAssets(r)}
          >
            资源
          </Button>
          {r.customer_status !== CustomerStatusCode.TERMINATED && (
            <Button
              type="link"
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => {
                setTerminateReason('');
                setTerminateTarget(r);
              }}
            >
              终止
            </Button>
          )}
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => crud.handleDelete(r)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  return (
    <div>
      <DataTable<Customer>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="id"
        total={data?.total}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={() => refetch()}
        toolbar={
          <Button type="primary" icon={<PlusOutlined />} onClick={crud.handleAdd}>
            新增客户
          </Button>
        }
      />
      <CustomerForm
        open={crud.formOpen}
        editRecord={crud.editRecord}
        onCancel={() => crud.closeForm()}
      />
      <Modal
        title="终止客户"
        open={terminateTarget !== null}
        onCancel={() => setTerminateTarget(null)}
        confirmLoading={terminateMutation.isPending}
        okText="确定终止"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        onOk={async () => {
          if (!terminateTarget) return;
          try {
            await terminateMutation.mutateAsync({
              id: terminateTarget.id,
              reason: terminateReason.trim() || undefined
            });
            message.success('客户已终止');
            setTerminateTarget(null);
          } catch (e: any) {
            message.error(e?.response?.data?.message || '终止失败');
          }
        }}
      >
        <p style={{ marginBottom: 12 }}>终止将不可逆地释放该客户名下全部资源，确定操作？</p>
        <Input.TextArea
          value={terminateReason}
          onChange={(e) => setTerminateReason(e.target.value)}
          placeholder="请输入终止原因（选填）"
          rows={3}
          maxLength={255}
          showCount
        />
      </Modal>
    </div>
  );
}

export default Customers;
