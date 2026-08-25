/**
 * 登录日志管理页面
 * - 支持按时间段、用户筛选
 * - 支持从用户管理页面跳转并自动筛选指定用户
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Table, DatePicker, Select, Space, Card, Tag, Button } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAllLoginLogs, type LoginLogQueryParams, type LoginLog } from '@/services/user';
import { useUserList } from '@/services/user';
import { LOGIN_TYPE_MAP } from '@/types/enums';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;

function LoginLogs() {
  const [searchParams] = useSearchParams();
  const [userId, setUserId] = useState<number | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: usersData } = useUserList({ per_page: 999 });
  const userOptions = (usersData?.items ?? []).map((u) => ({
    label: `${u.name || u.username}${u.department ? ` (${u.department})` : ''}`,
    value: u.id,
  }));

  useEffect(() => {
    const uid = searchParams.get('user_id');
    if (uid) {
      setUserId(Number(uid));
    }
  }, [searchParams]);

  const queryParams: LoginLogQueryParams = {
    page,
    per_page: pageSize,
    ...(userId ? { user_id: userId } : {}),
    ...(dateRange?.[0] ? { start_time: dateRange[0]!.startOf('day').toISOString() } : {}),
    ...(dateRange?.[1] ? { end_time: dateRange[1]!.endOf('day').toISOString() } : {}),
  };

  const { data, isLoading, refetch } = useAllLoginLogs(queryParams);

  const handleReset = () => {
    setUserId(undefined);
    setDateRange(null);
    setPage(1);
  };

  const columns = [
    {
      title: '登录时间',
      dataIndex: 'login_time',
      key: 'login_time',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '用户姓名',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (v: string | null) => v || '-',
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'IP地址',
      dataIndex: 'login_ip',
      key: 'login_ip',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: '登录类型',
      dataIndex: 'login_type',
      key: 'login_type',
      width: 100,
      render: (v: string) => {
        const m = LOGIN_TYPE_MAP[v];
        return <Tag color={m?.color ?? 'default'}>{(m?.label ?? v) || 'Web'}</Tag>;
      },
    },
    {
      title: '设备/浏览器',
      dataIndex: 'user_agent',
      key: 'user_agent',
      render: (v: string | null) => v || '-',
      ellipsis: true,
    },
  ];

  return (
    <Card>
      {/* 筛选栏 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <span style={{ color: '#666' }}>用户：</span>
        <Select
          value={userId}
          onChange={(v) => { setUserId(v); setPage(1); }}
          placeholder="全部用户"
          allowClear
          style={{ width: 200 }}
          options={userOptions}
        />
        <span style={{ color: '#666' }}>时间：</span>
        <RangePicker
          value={dateRange}
          onChange={(dates) => { setDateRange(dates); setPage(1); }}
          style={{ width: 280 }}
        />
        <Button icon={<SearchOutlined />} type="primary" onClick={() => { setPage(1); refetch(); }}>
          查询
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleReset}>
          重置
        </Button>
      </Space>

      {/* 日志表格 */}
      <Table<LoginLog>
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

export default LoginLogs;
