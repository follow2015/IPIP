import { useConfirm } from '@/utils/confirm';
import { Button, Space, Select } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNetworkList, useDeleteNetwork, useUpdateNetworkCustomer } from '@/services/network';
import { useAllocatableCustomerOptions } from '@/services/customer';
import type { IPNetwork } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { serverPagination } from '@/components/DataTable/serverPagination';
import DataTable from '@/components/DataTable';

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
      render: (_: unknown, record: IPNetwork) => renderNetworkActions(record)
    }
  ];

  const renderNetworkActions = (record: IPNetwork) => (
    <Space wrap>
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
  );

  const renderNetworkCard = (record: IPNetwork) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontWeight: 500 }}>{record.ip_network}</div>
      <div style={{ fontSize: 12, color: '#666' }}>
        {record.switch_name || '-'} / {record.port || '-'}
      </div>
      <div style={{ fontSize: 12, color: '#666' }}>{record.room_name || '-'}</div>
      <div style={{ fontSize: 12, color: '#666' }}>
        {t('networkList.field.customer')}: {record.customer_name || '-'}
      </div>
      <div style={{ fontSize: 12, color: '#666' }}>
        {t('networkList.field.nexthop')}: {record.nexthop || '-'}
      </div>
      {record.notes && <div style={{ fontSize: 12, color: '#999' }}>{record.notes}</div>}
      {renderNetworkActions(record)}
    </div>
  );

  return (
    <DataTable
      columns={columns}
      dataSource={data?.items ?? []}
      rowKey="id"
      loading={isLoading}
      size="small"
      searchable={false}
      showCard={false}
      mobileCardMode
      cardRender={renderNetworkCard}
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
