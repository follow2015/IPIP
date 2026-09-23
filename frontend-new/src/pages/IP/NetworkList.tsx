import { useConfirm } from '@/utils/confirm';
import { Table, Button, Space, Select } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNetworkList, useDeleteNetwork, useUpdateNetworkCustomer } from '@/services/network';
import { useAllocatableCustomerOptions } from '@/services/customer';
import type { IPNetwork } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { serverPagination } from '@/components/DataTable/serverPagination';

function NetworkList() {
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const deleteNetwork = useDeleteNetwork();
  const updateCustomer = useUpdateNetworkCustomer();
  const message = useMessage();
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const { data, isLoading, refetch } = useNetworkList({ per_page: 100 });

  const handleDelete = (record: IPNetwork) => {
    if (!record.room_id || !record.switch_id || !record.notes || !record.nexthop) {
      message.warning(t('networkList.message.missingParams'));
      return;
    }
    confirm({
      title: tc('confirm.deleteTitle'),
      content: t('networkList.confirm.deleteContent', { network: record.ip_network }),
      onOk: async () => {
        await deleteNetwork.mutateAsync({
          ipNetwork: record.ip_network,
          networkId: record.id
        });
        message.success(tc('message.deleteSuccess'));
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
        message.success(t('networkList.message.customerUpdated'));
        refetch();
      })
      .catch(() => message.error(t('networkList.message.updateFailed')));
  };

  const columns = [
    { title: t('networkList.field.network'), dataIndex: 'ip_network', key: 'ip_network' },
    {
      title: t('networkList.field.switch'),
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.port'),
      dataIndex: 'port',
      key: 'port',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.room'),
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.nexthop'),
      dataIndex: 'nexthop',
      key: 'nexthop',
      render: (v: string) => v || '-'
    },
    {
      title: t('networkList.field.notes'),
      dataIndex: 'notes',
      key: 'notes',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.actions'),
      key: 'action',
      render: (_: unknown, record: IPNetwork) => (
        <Space>
          <Select
            placeholder={t('networkList.action.assignCustomer')}
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
            {t('networkList.action.delete')}
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
      pagination={serverPagination({
        showSizeChanger: false,
        current: data?.page ?? 1,
        pageSize: data?.per_page ?? 20,
        total: data?.total ?? 0,
        showTotal: (total) => tc('pagination.total', { count: total })
      })}
      scroll={{ x: 'max-content' }}
    />
  );
}

export default NetworkList;
