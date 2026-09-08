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
import { IP_AUDIT_ACTION_MAP, IP_AUDIT_ACTION_OPTIONS } from '@/types/status-codes.generated';
import type { User } from '@/types/models';
import { formatDateTime } from '@/utils/format';

function ActionTag({ action }: { action: string }) {
  const meta = IP_AUDIT_ACTION_MAP[action as keyof typeof IP_AUDIT_ACTION_MAP];
  return <Tag color={meta?.color ?? 'default'}>{meta?.label ?? action}</Tag>;
}

export default function IPAudit() {
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
      if (u.id != null) map.set(u.id, u.name || u.username || `用户 #${u.id}`);
    }
    return map;
  }, [users]);

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
    id == null ? '-' : (userNameMap.get(id) ?? `用户 #${id}`);

  const columns: ColumnsType<IPAuditLog> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string | null) => (t ? formatDateTime(t) : '-')
    },
    {
      title: '操作人',
      dataIndex: 'operator_id',
      key: 'operator_id',
      width: 110,
      render: renderOperator
    },
    { title: 'IP 地址', dataIndex: 'ip_address', key: 'ip_address', width: 140 },
    {
      title: '机房',
      dataIndex: 'room_id',
      key: 'room_id',
      width: 130,
      render: (id: number | null) => (id == null ? '-' : (roomNameMap.get(id) ?? `机房 #${id}`))
    },
    {
      title: '动作',
      dataIndex: 'action',
      key: 'action',
      width: 90,
      render: (a: string) => <ActionTag action={a} />
    },
    {
      title: '归属客户',
      key: 'customer',
      width: 150,
      render: (_, record) => (record.source === 'allocation' ? (record.customer_name ?? '-') : '-')
    },
    {
      title: '详情',
      key: 'action_btn',
      width: 80,
      render: (_, record) => (
        <Button type="link" onClick={() => setDetail(record)}>
          查看
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
        searchPlaceholder="搜索 IP 地址..."
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
                label: '动作',
                type: 'select',
                options: IP_AUDIT_ACTION_OPTIONS,
                width: 120
              },
              {
                key: 'room_id',
                label: '机房',
                type: 'select',
                options: roomOptions ?? [],
                width: 150
              },
              {
                key: 'date_range',
                label: '时间',
                type: 'rangePicker',
                placeholders: ['开始日期', '结束日期']
              }
            ]}
          />
        }
      />

      <Modal
        title="审计记录详情"
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width="90%"
        style={{ maxWidth: 640 }}
      >
        {detail && (
          <Card size="small" type="inner">
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="时间" span={2}>
                {detail.created_at ? formatDateTime(detail.created_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="操作人">
                {renderOperator(detail.operator_id)}
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {detail.source === 'allocation' ? '归属变更' : '封禁/解封'}
              </Descriptions.Item>
              <Descriptions.Item label="IP 地址">{detail.ip_address}</Descriptions.Item>
              <Descriptions.Item label="机房">
                {detail.room_id == null
                  ? '-'
                  : (roomNameMap.get(detail.room_id) ?? `机房 #${detail.room_id}`)}
              </Descriptions.Item>
              <Descriptions.Item label="动作">
                <ActionTag action={detail.action} />
              </Descriptions.Item>
              {detail.source === 'allocation' ? (
                <Descriptions.Item label="归属客户">
                  {detail.customer_name ?? '-'}
                </Descriptions.Item>
              ) : (
                <Descriptions.Item label="封禁方式">{detail.ban_mode ?? '-'}</Descriptions.Item>
              )}
            </Descriptions>
            <Card size="small" title="详情（detail）" type="inner" style={{ marginTop: 12 }}>
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
