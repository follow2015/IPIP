/**
 * 审计日志页面
 * - 只读列表，支持多维筛选
 * - 顶部：时间范围筛选 + 操作类型筛选 + 资源类型筛选
 * - 参考 LoginLogs/index.tsx 的只读列表模式
 */
import { useState } from 'react';
import { Table, DatePicker, Select, Space, Card, Tag, Button } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuditLogs, type AuditLogQueryParams } from '@/services/audit';
import type { AuditLog } from '@/types/models';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;


const ACTION_OPTIONS = [
  { label: '创建', value: 'create' },
  { label: '更新', value: 'update' },
  { label: '删除', value: 'delete' },
  { label: '登录', value: 'login' },
  { label: '登出', value: 'logout' },
  { label: '导入', value: 'import' },
  { label: '导出', value: 'export' },
];


const RESOURCE_OPTIONS = [
  { label: '设备', value: 'device' },
  { label: '机柜', value: 'cabinet' },
  { label: '机房', value: 'room' },
  { label: 'IP', value: 'ip' },
  { label: '网段', value: 'network' },
  { label: '交换机', value: 'switch' },
  { label: '客户', value: 'customer' },
  { label: '用户', value: 'user' },
  { label: 'VLAN', value: 'vlan' },
  { label: '角色', value: 'role' },
];


const ACTION_COLOR_MAP: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  login: 'cyan',
  logout: 'default',
  import: 'purple',
  export: 'orange',
};


function AuditLogs() {
  const [action, setAction] = useState<string | undefined>();
  const [resource, setResource] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  
  const queryParams: AuditLogQueryParams = {
    page,
    per_page: pageSize,
    ...(action ? { action } : {}),
    ...(resource ? { resource } : {}),
    ...(dateRange?.[0] ? { start_time: dateRange[0]!.startOf('day').toISOString() } : {}),
    ...(dateRange?.[1] ? { end_time: dateRange[1]!.endOf('day').toISOString() } : {}),
  };

  const { data, isLoading, refetch } = useAuditLogs(queryParams);

  
  const handleReset = () => {
    setAction(undefined);
    setResource(undefined);
    setDateRange(null);
    setPage(1);
  };

  
  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作人',
      dataIndex: 'user_id',
      key: 'user_id',
      width: 100,
      render: (v: number | null) => v ? `用户 #${v}` : '-',
    },
    {
      title: '操作类型',
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (v: string) => (
        <Tag color={ACTION_COLOR_MAP[v] ?? 'default'}>{v}</Tag>
      ),
    },
    {
      title: '资源类型',
      dataIndex: 'resource',
      key: 'resource',
      width: 100,
      render: (v: string) => v || '-',
    },
    {
      title: '资源ID',
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 100,
      render: (v: number | null) => v ?? '-',
    },
    {
      title: '客户端IP',
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: '详情',
      dataIndex: 'detail',
      key: 'detail',
      render: (v: Record<string, unknown> | null) => {
        if (!v) return '-';
        const text = JSON.stringify(v);
        return text.length > 100 ? text.slice(0, 100) + '...' : text;
      },
      ellipsis: true,
    },
  ];

  return (
    <Card>
      {}
      <Space style={{ marginBottom: 16 }} wrap>
        <span style={{ color: '#666' }}>时间：</span>
        <RangePicker
          value={dateRange}
          onChange={(dates) => { setDateRange(dates); setPage(1); }}
          style={{ width: 280 }}
        />
        <span style={{ color: '#666' }}>操作类型：</span>
        <Select
          value={action}
          onChange={(v) => { setAction(v); setPage(1); }}
          placeholder="全部操作"
          allowClear
          style={{ width: 140 }}
          options={ACTION_OPTIONS}
        />
        <span style={{ color: '#666' }}>资源类型：</span>
        <Select
          value={resource}
          onChange={(v) => { setResource(v); setPage(1); }}
          placeholder="全部资源"
          allowClear
          style={{ width: 140 }}
          options={RESOURCE_OPTIONS}
        />
        <Button icon={<SearchOutlined />} type="primary" onClick={() => { setPage(1); refetch(); }}>
          查询
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleReset}>
          重置
        </Button>
      </Space>

      {}
      <Table<AuditLog>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="id"
        pagination={{
          total: data?.total ?? 0,
          pageSize,
          current: page,
          showTotal: (t) => `共 ${t} 条`,
          showSizeChanger: true,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
        size="small"
      />
    </Card>
  );
}

export default AuditLogs;
