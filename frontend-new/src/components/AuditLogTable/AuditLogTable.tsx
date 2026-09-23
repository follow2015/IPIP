import { useState, useMemo } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Button,
  Descriptions,
  Modal,
  Alert,
  Select,
  DatePicker
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { useAuditLogs } from '@/services/audit';
import { get } from '@/services/api-client';
import type { AuditLog, User } from '@/types/models';
import { serverPagination } from '@/components/DataTable/serverPagination';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;

export interface AuditLogTableProps {
  title: React.ReactNode;
  actionPrefix?: string;
  resourceOptions?: { label: string; value: string }[];
  actionOptions?: { label: string; value: string }[];
  actionColorMap?: Record<string, string>;
}

export default function AuditLogTable({
  title,
  actionPrefix,
  resourceOptions,
  actionOptions,
  actionColorMap = {}
}: AuditLogTableProps) {
  const { t } = useTranslation('settings');
  const { t: tCommon } = useTranslation('common');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [action, setAction] = useState<string | undefined>(actionPrefix);
  const [resource, setResource] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [detailRecord, setDetailRecord] = useState<AuditLog | null>(null);

  const { data: users } = useQuery({
    queryKey: ['users', 'all-for-audit'],
    queryFn: async () => {
      const res = await get<User[]>('/users', { all: 'true' });
      return res.data ?? [];
    },
    staleTime: 5 * 60 * 1000 // 用户列表 5 分钟缓存
  });
  const userNameMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const u of users ?? []) {
      if (u.id != null) {
        map.set(u.id, u.name || u.username || t('audit.userFallback', { id: u.id }));
      }
    }
    return map;
  }, [users, t]);
  const renderUserName = (userId: number | null) => {
    if (userId == null) return '-';
    return userNameMap.get(userId) ?? t('audit.userFallback', { id: userId });
  };

  const { data, isLoading, isError, error, refetch, isFetching } = useAuditLogs({
    action,
    resource,
    ...(dateRange?.[0] ? { start_time: dateRange[0]!.startOf('day').toISOString() } : {}),
    ...(dateRange?.[1] ? { end_time: dateRange[1]!.endOf('day').toISOString() } : {}),
    page,
    per_page: pageSize
  });

  const logs = data?.items ?? [];
  const total = data?.total ?? 0;

  const handleReset = () => {
    setAction(actionPrefix);
    setResource(undefined);
    setDateRange(null);
    setPage(1);
  };

  const columns: ColumnsType<AuditLog> = [
    {
      title: tCommon('field.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => (v ? formatDateTime(v) : '-')
    },
    {
      title: t('audit.column.operator'),
      dataIndex: 'user_id',
      key: 'user_id',
      width: 100,
      render: (v: number | null) => renderUserName(v)
    },
    {
      title: t('audit.column.action'),
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (a: string) => <Tag color={actionColorMap[a] ?? 'blue'}>{a}</Tag>
    },
    {
      title: t('audit.column.resource'),
      dataIndex: 'resource',
      key: 'resource',
      width: 120,
      render: (r: string) => (r ? <Tag>{r}</Tag> : '-')
    },
    {
      title: t('audit.column.resourceId'),
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 80,
      render: (v: number | null) => v ?? '-'
    },
    {
      title: t('audit.column.clientIp'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 130,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: tCommon('action.detail'),
      key: 'action_btn',
      width: 80,
      render: (_, record) => (
        <Button type="link" onClick={() => setDetailRecord(record)}>
          {tCommon('action.view')}
        </Button>
      )
    }
  ];

  return (
    <Card
      title={title}
      extra={
        <Space wrap>
          {actionOptions && (
            <Select
              value={action}
              onChange={(v) => {
                setAction(v);
                setPage(1);
              }}
              options={actionOptions}
              style={{ width: 180 }}
              allowClear
              placeholder={t('audit.filter.actionType')}
            />
          )}
          {resourceOptions && (
            <Select
              value={resource}
              onChange={(v) => {
                setResource(v);
                setPage(1);
              }}
              options={resourceOptions}
              style={{ width: 140 }}
              allowClear
              placeholder={t('audit.filter.resourceType')}
            />
          )}
          <RangePicker
            value={dateRange as [dayjs.Dayjs, dayjs.Dayjs] | null}
            onChange={(v) => {
              setDateRange(v as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null);
              setPage(1);
            }}
            style={{ width: 240 }}
          />
          <Button onClick={handleReset}>{tCommon('action.reset')}</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching}>
            {tCommon('action.refresh')}
          </Button>
        </Space>
      }
    >
      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={t('audit.loadFailed')}
          description={error instanceof Error ? error.message : undefined}
          action={
            <Button size="small" onClick={() => refetch()}>
              {tCommon('action.retry')}
            </Button>
          }
        />
      )}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={logs}
        loading={isLoading}
        size="middle"
        scroll={{ x: 'max-content' }}
        pagination={serverPagination({
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (total) => tCommon('pagination.total', { count: total }),
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          }
        })}
      />

      <Modal
        title={t('audit.detailTitle')}
        open={!!detailRecord}
        onCancel={() => setDetailRecord(null)}
        footer={null}
        width="90%"
        style={{ maxWidth: 640 }}
      >
        {detailRecord && (
          <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
            <Descriptions column={{ xs: 1, sm: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label="ID">{detailRecord.id}</Descriptions.Item>
              <Descriptions.Item label={tCommon('field.time')}>
                {detailRecord.created_at ? formatDateTime(detailRecord.created_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.column.operator')}>
                {renderUserName(detailRecord.user_id)}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.column.action')}>
                <Tag color={actionColorMap[detailRecord.action] ?? 'blue'}>
                  {detailRecord.action}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.column.resource')}>{detailRecord.resource ?? '-'}</Descriptions.Item>
              <Descriptions.Item label={t('audit.column.resourceId')}>
                {detailRecord.resource_id ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('audit.column.clientIp')} span={2}>
                {detailRecord.ip_address ?? '-'}
              </Descriptions.Item>
            </Descriptions>
            <Card size="small" title={t('audit.detailRawTitle')} type="inner">
              <pre style={{ maxHeight: 300, overflow: 'auto', fontSize: 12, margin: 0 }}>
                {JSON.stringify(detailRecord.detail, null, 2)}
              </pre>
            </Card>
          </Space>
        )}
      </Modal>
    </Card>
  );
}
