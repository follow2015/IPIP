import { useMemo, useState } from 'react';
import { Button, Card, Descriptions, Modal, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import type { ColumnsType } from 'antd/es/table';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import { useTable } from '@/hooks/useTable';
import { get } from '@/services/api-client';
import { useIPAuditLogs } from '@/services/ip-audit';
import type { IPAuditLog } from '@/services/ip-audit';
import { useRoomOptions } from '@/services/room';
import { getIPAuditActionMeta, getIPAuditActionOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { User } from '@/types/models';
import { formatDateTime } from '@/utils/format';

function ActionTag({ action }: { action: string }) {
  const { t: td } = useTranslation('device');
  const meta = getIPAuditActionMeta(action, td);
  return <Tag color={meta?.color ?? 'default'}>{meta?.label ?? action}</Tag>;
}

export default function IPAudit() {
  const { t: td } = useTranslation('device');
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const table = useTable();
  const [detail, setDetail] = useState<IPAuditLog | null>(null);

  const dateRange = table.filters.date_range as string | undefined;
  const [startDate, endDate] = dateRange ? dateRange.split('~') : [undefined, undefined];

  const { data, isLoading, refetch } = useIPAuditLogs({
    page: table.page,
    per_page: table.perPage,
    action: (table.filters.action as string) || undefined,
    ip_address: table.search || undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    start_time: startDate,
    end_time: endDate ? `${endDate}T23:59:59` : undefined
  });

  const { data: users } = useQuery({
    queryKey: ['users', 'all-for-audit'],
    queryFn: async () => {
      const res = await get<User[]>('/users', { all: 'true' });
      return res.data ?? [];
    },
    staleTime: 5 * 60 * 1000
  });
  const userNameMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const u of users ?? []) {
      if (u.id != null) map.set(u.id, u.name || u.username || t('audit.userFallback', { id: u.id }));
    }
    return map;
  }, [users, t]);

  const { data: roomOptions } = useRoomOptions();
  const roomNameMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const o of roomOptions ?? []) {
      const id = Number(o.value);
      if (!Number.isNaN(id)) map.set(id, o.label);
    }
    return map;
  }, [roomOptions]);

  const renderOperator = (id: number | null) =>
    id == null ? '-' : (userNameMap.get(id) ?? t('audit.userFallback', { id }));

  const columns: ColumnsType<IPAuditLog> = [
    {
      title: t('audit.field.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string | null) => (t ? formatDateTime(t) : '-')
    },
    {
      title: t('audit.field.operator'),
      dataIndex: 'operator_id',
      key: 'operator_id',
      width: 110,
      render: renderOperator
    },
    { title: t('audit.field.ipAddress'), dataIndex: 'ip_address', key: 'ip_address', width: 140 },
    {
      title: t('audit.field.room'),
      dataIndex: 'room_id',
      key: 'room_id',
      width: 130,
      render: (id: number | null) =>
        id == null ? '-' : (roomNameMap.get(id) ?? t('audit.roomFallback', { id }))
    },
    {
      title: t('audit.field.action'),
      dataIndex: 'action',
      key: 'action',
      width: 90,
      render: (a: string) => <ActionTag action={a} />
    },
    {
      title: t('audit.field.customer'),
      key: 'customer',
      width: 150,
      render: (_, record) => (record.source === 'allocation' ? (record.customer_name ?? '-') : '-')
    },
    {
      title: t('audit.field.detail'),
      key: 'action_btn',
      width: 80,
      render: (_, record) => (
        <Button type="link" onClick={() => setDetail(record)}>
          {t('audit.action.view')}
        </Button>
      )
    }
  ];

  return (
    <>
      <DataTable<IPAuditLog>
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder={t('audit.searchPlaceholder')}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={refetch}
        total={data?.total ?? 0}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        toolbar={
          <FilterBar
            table={table}
            filters={[
              {
                key: 'action',
                label: t('audit.field.action'),
                type: 'select',
                options: getIPAuditActionOptions(td),
                width: 120
              },
              {
                key: 'room_id',
                label: t('audit.field.room'),
                type: 'select',
                options: roomOptions ?? [],
                width: 150
              },
              {
                key: 'date_range',
                label: t('audit.field.time'),
                type: 'rangePicker',
                placeholders: [tc('range.startDate'), tc('range.endDate')]
              }
            ]}
          />
        }
      />

      <Modal
        title={t('audit.detail.title')}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width="90%"
        style={{ maxWidth: 640 }}
      >
        {detail && (
          <Card size="small" type="inner">
            <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label={t('audit.field.time')} span={2}>
                {detail.created_at ? formatDateTime(detail.created_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.field.operator')}>
                {renderOperator(detail.operator_id)}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.detail.source')}>
                {detail.source === 'allocation'
                  ? t('audit.detail.sourceAllocation')
                  : t('audit.detail.sourceBan')}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.field.ipAddress')}>
                {detail.ip_address}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.field.room')}>
                {detail.room_id == null
                  ? '-'
                  : (roomNameMap.get(detail.room_id) ??
                    t('audit.roomFallback', { id: detail.room_id }))}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.field.action')}>
                <ActionTag action={detail.action} />
              </Descriptions.Item>
              {detail.source === 'allocation' ? (
                <Descriptions.Item label={t('audit.field.customer')}>
                  {detail.customer_name ?? '-'}
                </Descriptions.Item>
              ) : (
                <Descriptions.Item label={t('audit.detail.banMode')}>
                  {detail.ban_mode ?? '-'}
                </Descriptions.Item>
              )}
            </Descriptions>
            <Card
              size="small"
              title={t('audit.detail.detailTitle')}
              type="inner"
              style={{ marginTop: 12 }}
            >
              <pre style={{ maxHeight: 300, overflow: 'auto', fontSize: 12, margin: 0 }}>
                {JSON.stringify(detail.detail, null, 2)}
              </pre>
            </Card>
          </Card>
        )}
      </Modal>
    </>
  );
}
