import { confirm } from '@/utils/confirm';
import { Table, Button, Space, Select } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useNetworkList, useDeleteNetwork, useUpdateNetworkCustomer } from '@/services/network';
import { useAllocatableCustomerOptions } from '@/services/customer';
import type { IPNetwork } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';

function NetworkList() {
  const deleteNetwork = useDeleteNetwork();
  const updateCustomer = useUpdateNetworkCustomer();
  const message = useMessage();
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const { data, isLoading, refetch } = useNetworkList({ per_page: 100 });

  const handleDelete = (record: IPNetwork) => {
    if (!record.room_id || !record.switch_id || !record.notes || !record.nexthop) {
      message.warning('缺少必要参数（room_id/switch_id/notes/nexthop），无法删除');
      return;
    }
    confirm({
      title: '确认删除',
      content: `确定要删除网段 ${record.ip_network} 吗？`,
      onOk: async () => {
        await deleteNetwork.mutateAsync({
          ipNetwork: record.ip_network,
          networkId: record.id
        });
        message.success('删除成功');
        refetch();
      }
    });
  };

  const handleUpdateCustomer = (record: IPNetwork, customerId: number | null) => {
    updateCustomer
      .mutateAsync({
        ipNetwork: record.ip_network,
        data: { network_id: record.id, customer_id: customerId }
      })
      .then(() => {
        message.success('客户更新成功');
        refetch();
      })
      .catch(() => message.error('更新失败'));
  };

  const columns = [
    { title: '网段', dataIndex: 'ip_network', key: 'ip_network' },
    {
      title: '交换机',
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    { title: '端口', dataIndex: 'port', key: 'port', render: (v: string | null) => v || '-' },
    {
      title: '机房',
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    { title: '下一跳', dataIndex: 'nexthop', key: 'nexthop', render: (v: string) => v || '-' },
    { title: '备注', dataIndex: 'notes', key: 'notes', render: (v: string | null) => v || '-' },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: IPNetwork) => (
        <Space>
          <Select
            placeholder="分配客户"
            options={customerOptions}
            allowClear
            style={{ width: 120 }}
            value={record.customer_id ?? undefined}
            onChange={(v) => handleUpdateCustomer(record, v ?? null)}
          />
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  return (
    <Table
      columns={columns}
      dataSource={data?.items ?? []}
      rowKey="id"
      loading={isLoading}
      size="small"
      pagination={{
        total: data?.total ?? 0,
        pageSize: data?.per_page ?? 20,
        current: data?.page ?? 1,
        showTotal: (t) => `共 ${t} 条`
      }}
    />
  );
}

export default NetworkList;
