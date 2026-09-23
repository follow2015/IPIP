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
import { Button, Space, Tag, Modal, Input } from 'antd';
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
import { CustomerStatusCode } from '@/types/enums';
import { getCustomerStatusMeta, type DeviceT } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useCrudPage } from '@/hooks/useCrudPage';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';

function renderStatus(v: number, t: DeviceT) {
  const s = getCustomerStatusMeta(v, t);
  if (v === undefined || v === null) return '-';
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}

function customerStatusLabel(v: number | null | undefined, t: DeviceT) {
  if (v === null || v === undefined) return '-';
  const s = getCustomerStatusMeta(v, t);
  return s ? s.label : String(v);
}

function buildCustomerInfoText(c: Customer, td: DeviceT, tc: TFunction<'common'>): string {
  return [
    td('customer.infoTitle'),
    `ID: ${c.id}`,
    `${td('customer.field.name')}: ${c.customer_name ?? '-'}`,
    `${tc('field.status')}: ${customerStatusLabel(c.customer_status, td)}`,
    `${td('customer.field.contactPerson')}: ${c.contact_person ?? '-'}`,
    `${td('customer.field.contactPhone')}: ${c.contact_phone ?? '-'}`,
    `${td('customer.field.email')}: ${c.email ?? '-'}`,
    `${td('customer.field.address')}: ${c.address ?? '-'}`
  ].join('\n');
}

function Customers() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const navigate = useNavigate();
  const message = useMessage();

  const crud = useCrudPage<Customer>({
    useList: useCustomerList,
    useDelete: useDeleteCustomer,
    nameKey: 'customer_name',
    nameLabel: tc('field.customer')
  });

  const { table, data, isLoading, refetch } = crud;

  const [terminateTarget, setTerminateTarget] = useState<Customer | null>(null);
  const [terminateReason, setTerminateReason] = useState('');
  const terminateMutation = useTerminateCustomer();

  const handleAssets = (r: Customer) => {
    navigate(`/customers/${r.id}`);
  };

  const handleCopy = (r: Customer) => {
    const text = buildCustomerInfoText(r, td, tc);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => message.success(td('customer.message.copied')))
        .catch(() => message.error(tc('message.copyFailedManual')));
    } else {
      message.error(tc('message.copyUnsupported'));
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
    { title: td('customer.field.name'), dataIndex: 'customer_name', key: 'customer_name', width: 160 },
    {
      title: tc('field.status'),
      dataIndex: 'customer_status',
      key: 'customer_status',
      width: 80,
      render: (v: number) => renderStatus(v, td)
    },
    {
      title: td('customer.field.contactPerson'),
      dataIndex: 'contact_person',
      key: 'contact_person',
      width: 100,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: td('customer.field.contactPhone'),
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      width: 130,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: td('customer.field.email'),
      dataIndex: 'email',
      key: 'email',
      width: 180,
      render: (v: string | null) => v ?? '-',
      ellipsis: true
    },
    {
      title: td('customer.field.address'),
      dataIndex: 'address',
      key: 'address',
      width: 200,
      render: (v: string | null) => v ?? '-',
      ellipsis: true
    },
    {
      title: tc('field.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 240,
      render: (_: unknown, r: Customer) => (
        <Space>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(r)}>
            {tc('action.copy')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => crud.handleEdit(r)}
          >
            {tc('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<BarChartOutlined />}
            onClick={() => handleAssets(r)}
          >
            {td('customer.action.resources')}
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
              {td('customer.action.terminate')}
            </Button>
          )}
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => crud.handleDelete(r)}
          >
            {tc('action.delete')}
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
            {td('customer.add')}
          </Button>
        }
      />
      <CustomerForm
        open={crud.formOpen}
        editRecord={crud.editRecord}
        onCancel={() => crud.closeForm()}
      />
      <Modal
        title={td('customer.terminate.title')}
        open={terminateTarget !== null}
        onCancel={() => setTerminateTarget(null)}
        confirmLoading={terminateMutation.isPending}
        okText={td('customer.terminate.ok')}
        cancelText={tc('action.cancel')}
        okButtonProps={{ danger: true }}
        onOk={async () => {
          if (!terminateTarget) return;
          try {
            await terminateMutation.mutateAsync({
              id: terminateTarget.id,
              reason: terminateReason.trim() || undefined
            });
            message.success(td('customer.message.terminated'));
            setTerminateTarget(null);
          } catch (e: any) {
            message.error(e?.response?.data?.message || td('customer.message.terminateFailed'));
          }
        }}
      >
        <p style={{ marginBottom: 12 }}>{td('customer.terminate.confirmContent')}</p>
        <Input.TextArea
          value={terminateReason}
          onChange={(e) => setTerminateReason(e.target.value)}
          placeholder={td('customer.terminate.reasonPlaceholder')}
          rows={3}
          maxLength={255}
          showCount
        />
      </Modal>
    </div>
  );
}

export default Customers;
