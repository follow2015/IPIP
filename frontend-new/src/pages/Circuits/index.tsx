import { useMemo, useState } from 'react';
import { Button, Tag, Tooltip, theme } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import { useCrudPage } from '@/hooks/useCrudPage';
import {
  useCircuitList,
  useDeleteCircuit,
  type BillingMode,
  type Circuit,
  type CircuitQueryParams,
  type CircuitStatus
} from '@/services/circuit';
import { useCarrierOptions } from '@/services/carrier';
import { formatDateTime } from '@/utils/format';
import CircuitForm from './CircuitForm';
import CircuitDetail from './CircuitDetail';
import {
  BILLING_MODE_KEY,
  BILLING_MODE_VALUES,
  CIRCUIT_STATUS_COLOR,
  CIRCUIT_STATUS_KEY,
  CIRCUIT_STATUS_VALUES
} from './circuitMeta';

const EXPIRING_SOON_DAYS = 30;

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const target = Date.parse(`${dateStr}T00:00:00Z`);
  if (Number.isNaN(target)) return null;
  const today = Date.parse(`${new Date().toISOString().slice(0, 10)}T00:00:00Z`);
  return Math.round((target - today) / 86400000);
}

const { useToken } = theme;

function Circuits() {
  const { t } = useTranslation('circuit');
  const { t: tc } = useTranslation('common');
  const { token } = useToken();

  const { data: carrierOptions } = useCarrierOptions();

  const [detailId, setDetailId] = useState<number | null>(null);

  const crud = useCrudPage<Circuit, CircuitQueryParams>({
    useList: useCircuitList,
    useDelete: useDeleteCircuit,
    nameKey: 'circuit_no',
    nameLabel: t('title')
  });
  const { table, data, isLoading, refetch, handleAdd, handleEdit, handleDelete, closeForm, formOpen, editRecord } =
    crud;

  const columns = useMemo(
    () => [
      { title: t('field.circuitNo'), dataIndex: 'circuit_no', key: 'circuit_no', width: 160 },
      {
        title: tc('field.name'),
        dataIndex: 'name',
        key: 'name',
        width: 140,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('field.carrier'),
        dataIndex: 'carrier_id',
        key: 'carrier_id',
        width: 140,
        render: (v: number | null, r: Circuit) => r.carrier_name || (v ? String(v) : '-')
      },
      {
        title: t('field.customer'),
        dataIndex: 'customer_id',
        key: 'customer_id',
        width: 140,
        render: (v: number | null, r: Circuit) => r.customer_name || (v ? String(v) : '-')
      },
      {
        title: t('field.status'),
        dataIndex: 'status',
        key: 'status',
        width: 90,
        render: (v: CircuitStatus | null) =>
          v ? (
            <Tag color={CIRCUIT_STATUS_COLOR[v] ?? 'default'}>{t(CIRCUIT_STATUS_KEY[v])}</Tag>
          ) : (
            '-'
          )
      },
      {
        title: t('field.bandwidth'),
        dataIndex: 'bandwidth_display',
        key: 'bandwidth_display',
        width: 110,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('field.billingMode'),
        dataIndex: 'billing_mode',
        key: 'billing_mode',
        width: 140,
        render: (v: BillingMode | null) => (v ? t(BILLING_MODE_KEY[v]) : '-')
      },
      {
        title: t('field.endDate'),
        dataIndex: 'end_date',
        key: 'end_date',
        width: 130,
        render: (v: string | null) => {
          if (!v) return '-';
          const left = daysUntil(v);
          if (left === null || left > EXPIRING_SOON_DAYS) return v;
          return (
            <Tooltip title={left < 0 ? t('expiry.expired') : t('expiry.daysLeft', { days: left })}>
              <span style={{ color: token.colorError }}>{v}</span>
            </Tooltip>
          );
        }
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
        width: 200,
        render: (_: unknown, r: Circuit) => (
          <>
            <Button type="link" size="small" onClick={() => setDetailId(r.id)}>
              {t('detail.action.open')}
            </Button>
            <Button type="link" size="small" onClick={() => handleEdit(r)}>
              {tc('action.edit')}
            </Button>
            <Button type="link" size="small" danger onClick={() => handleDelete(r)}>
              {tc('action.delete')}
            </Button>
          </>
        )
      }
    ],
    [handleEdit, handleDelete, t, tc, token]
  );

  return (
    <div>
      <DataTable<Circuit>
        error={crud.error}
        onRetry={crud.refetch}
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder={t('searchPlaceholder')}
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
                label: t('filter.byStatus'),
                type: 'select',
                width: 120,
                options: CIRCUIT_STATUS_VALUES.map((v) => ({
                  label: t(CIRCUIT_STATUS_KEY[v]),
                  value: v
                }))
              },
              {
                key: 'carrier_id',
                label: t('filter.byCarrier'),
                type: 'select',
                width: 160,
                options: carrierOptions ?? []
              },
              {
                key: 'billing_mode',
                label: t('filter.byBillingMode'),
                type: 'select',
                width: 160,
                options: BILLING_MODE_VALUES.map((v) => ({
                  label: t(BILLING_MODE_KEY[v]),
                  value: v
                }))
              }
            ]}
            table={table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                {t('action.add')}
              </Button>
            }
          />
        }
      />

      <CircuitForm
        open={formOpen}
        record={editRecord}
        onCancel={closeForm}
        onSuccess={() => {
          closeForm();
          refetch();
        }}
      />

      <CircuitDetail
        circuitId={detailId}
        open={detailId !== null}
        onClose={() => setDetailId(null)}
      />
    </div>
  );
}

export default Circuits;
