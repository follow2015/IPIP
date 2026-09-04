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
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { useAuditLogs } from '@/services/audit';
import { get } from '@/services/api-client';
import type { AuditLog, User } from '@/types/models';

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
        map.set(u.id, u.name || u.username || `用户 #${u.id}`);
      }
    }
    return map;
  }, [users]);
  const renderUserName = (userId: number | null) => {
    if (userId == null) return '-';
    return userNameMap.get(userId) ?? `用户 #${userId}`;
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
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-')
    },
    {
      title: '操作人',
      dataIndex: 'user_id',
      key: 'user_id',
      width: 100,
      render: (v: number | null) => renderUserName(v)
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (a: string) => <Tag color={actionColorMap[a] ?? 'blue'}>{a}</Tag>
    },
    {
      title: '资源',
      dataIndex: 'resource',
      key: 'resource',
      width: 120,
      render: (r: string) => (r ? <Tag>{r}</Tag> : '-')
    },
    {
      title: '资源ID',
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 80,
      render: (v: number | null) => v ?? '-'
    },
    {
      title: '客户端IP',
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 130,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '详情',
      key: 'action_btn',
      width: 80,
      render: (_, record) => (
        <Button type="link" onClick={() => setDetailRecord(record)}>
          查看
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
              placeholder="操作类型"
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
              placeholder="资源类型"
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
          <Button onClick={handleReset}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching}>
            刷新
          </Button>
        </Space>
      }
    >
      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="加载审计日志失败"
          description={error instanceof Error ? error.message : undefined}
          action={
            <Button size="small" onClick={() => refetch()}>
              重试
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
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          }
        }}
      />

      <Modal
        title="审计记录详情"
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
              <Descriptions.Item label="时间">
                {detailRecord.created_at
                  ? new Date(detailRecord.created_at).toLocaleString('zh-CN')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="操作人">
                {renderUserName(detailRecord.user_id)}
              </Descriptions.Item>
              <Descriptions.Item label="操作">
                <Tag color={actionColorMap[detailRecord.action] ?? 'blue'}>
                  {detailRecord.action}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="资源">{detailRecord.resource ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="资源ID">
                {detailRecord.resource_id ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="客户端IP" span={2}>
                {detailRecord.ip_address ?? '-'}
              </Descriptions.Item>
            </Descriptions>
            <Card size="small" title="详情（detail）" type="inner">
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
