import { useMemo } from 'react';
import { Button, Tag, Tooltip } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import { useCrudPage } from '@/hooks/useCrudPage';
import { useMessage } from '@/hooks/useMessage';
import {
  useCarrierList,
  useDeleteCarrier,
  type Carrier,
  type CarrierQueryParams,
  type CarrierStatus,
  type CarrierType
} from '@/services/carrier';
import { formatDateTime } from '@/utils/format';
import CarrierForm from './CarrierForm';

const CARRIER_STATUS_COLOR: Record<CarrierStatus, string> = {
  active: 'green',
  inactive: 'default'
};

const CARRIER_TYPE_KEY = {
  basic: 'carrier.type.basic',
  isp: 'carrier.type.isp',
  idc: 'carrier.type.idc',
  agent: 'carrier.type.agent'
} as const satisfies Record<CarrierType, string>;

const CARRIER_STATUS_KEY = {
  active: 'carrier.status.active',
  inactive: 'carrier.status.inactive'
} as const satisfies Record<CarrierStatus, string>;

function Carriers() {
  const { t } = useTranslation('circuit');
  const { t: tc } = useTranslation('common');
  const message = useMessage();

  const crud = useCrudPage<Carrier, CarrierQueryParams>({
    useList: useCarrierList,
    useDelete: useDeleteCarrier,
    nameKey: 'name',
    nameLabel: t('carrier.title')
  });
  const { table, data, isLoading, refetch, handleAdd, handleDelete, closeForm, formOpen } = crud;

  const columns = useMemo(
    () => [
      { title: tc('field.name'), dataIndex: 'name', key: 'name', width: 180 },
      {
        title: t('carrier.field.shortName'),
        dataIndex: 'short_name',
        key: 'short_name',
        width: 100,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('carrier.field.type'),
        dataIndex: 'carrier_type',
        key: 'carrier_type',
        width: 110,
        render: (v: CarrierType | null) => (v ? <Tag>{t(CARRIER_TYPE_KEY[v])}</Tag> : '-')
      },
      {
        title: t('carrier.field.status'),
        dataIndex: 'status',
        key: 'status',
        width: 90,
        render: (v: CarrierStatus | null) =>
          v ? (
            <Tag color={CARRIER_STATUS_COLOR[v] ?? 'default'}>{t(CARRIER_STATUS_KEY[v])}</Tag>
          ) : (
            '-'
          )
      },
      {
        title: t('carrier.field.hotline'),
        dataIndex: 'hotline',
        key: 'hotline',
        width: 140,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('carrier.field.contactPerson'),
        dataIndex: 'contact_person',
        key: 'contact_person',
        width: 100,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('carrier.field.sla'),
        dataIndex: 'default_sla_level',
        key: 'default_sla_level',
        width: 100,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('carrier.field.notes'),
        dataIndex: 'notes',
        key: 'notes',
        ellipsis: true,
        render: (v: string | null) =>
          v ? (
            <Tooltip title={v}>
              <span>{v}</span>
            </Tooltip>
          ) : (
            '-'
          )
      },
      {
        title: tc('field.updatedAt'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 150,
        render: (v: string) => formatDateTime(v)
      },
      {
        title: tc('field.actions'),
        key: 'action',
        width: 80,
        render: (_: unknown, r: Carrier) => (
          <Button type="link" size="small" danger onClick={() => handleDelete(r)}>
            {tc('action.delete')}
          </Button>
        )
      }
    ],
    [handleDelete, t, tc]
  );

  return (
    <div>
      <DataTable<Carrier>
        error={crud.error}
        onRetry={crud.refetch}
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder={tc('action.search')}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={() => refetch()}
        total={data?.total ?? 0}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        toolbar={
          <FilterBar
            filters={[
              {
                key: 'status',
                label: t('carrier.field.status'),
                type: 'select',
                width: 120,
                options: (Object.keys(CARRIER_STATUS_KEY) as CarrierStatus[]).map((v) => ({
                  label: t(CARRIER_STATUS_KEY[v]),
                  value: v
                }))
              },
              {
                key: 'carrier_type',
                label: t('carrier.field.type'),
                type: 'select',
                width: 140,
                options: (Object.keys(CARRIER_TYPE_KEY) as CarrierType[]).map((v) => ({
                  label: t(CARRIER_TYPE_KEY[v]),
                  value: v
                }))
              }
            ]}
            table={table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                {t('carrier.action.add')}
              </Button>
            }
          />
        }
      />

      <CarrierForm
        open={formOpen}
        onCancel={closeForm}
        onSuccess={() => {
          closeForm();
          refetch();
          message.success(t('message.createSuccess'));
        }}
      />
    </div>
  );
}

export default Carriers;
