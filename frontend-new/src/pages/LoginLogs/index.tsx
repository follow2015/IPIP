/**
 * 登录日志管理页面
 * - 支持按时间段、用户筛选
 * - 支持从用户管理页面跳转并自动筛选指定用户
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DatePicker, Select, Space, Card, Tag, Button } from 'antd';
import DataTable from '@/components/DataTable';
import { serverPagination } from '@/components/DataTable/serverPagination';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAllLoginLogs, type LoginLogQueryParams, type LoginLog } from '@/services/user';
import { useUserList } from '@/services/user';
import { getLoginTypeMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';

const { RangePicker } = DatePicker;

function LoginLogs() {
  const { t } = useTranslation('device');
  const { t: ts } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [searchParams] = useSearchParams();
  const [userId, setUserId] = useState<number | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: usersData } = useUserList({ per_page: 999 });
  const userOptions = (usersData?.items ?? []).map((u) => ({
    label: `${u.name || u.username}${u.department ? ` (${u.department})` : ''}`,
    value: u.id
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
    ...(dateRange?.[1] ? { end_time: dateRange[1]!.endOf('day').toISOString() } : {})
  };

  const { data, isLoading, refetch } = useAllLoginLogs(queryParams);

  const handleReset = () => {
    setUserId(undefined);
    setDateRange(null);
    setPage(1);
  };

  const columns = [
    {
      title: ts('loginLog.column.loginTime'),
      dataIndex: 'login_time',
      key: 'login_time',
      width: 180,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: ts('loginLog.column.userFullName'),
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (v: string | null) => v || '-'
    },
    {
      title: ts('loginLog.column.username'),
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (v: string | null) => v || '-'
    },
    {
      title: ts('loginLog.column.ipAddress'),
      dataIndex: 'login_ip',
      key: 'login_ip',
      width: 140,
      render: (v: string | null) => v || '-'
    },
    {
      title: ts('loginLog.column.loginType'),
      dataIndex: 'login_type',
      key: 'login_type',
      width: 100,
      render: (v: string) => {
        const m = getLoginTypeMeta(v, t);
        return <Tag color={m?.color ?? 'default'}>{(m?.label ?? v) || 'Web'}</Tag>;
      }
    },
    {
      title: ts('loginLog.column.userAgent'),
      dataIndex: 'user_agent',
      key: 'user_agent',
      render: (v: string | null) => v || '-',
      ellipsis: true
    }
  ];

  return (
    <Card>
      {/* 筛选栏 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <span style={{ color: '#666' }}>{ts('loginLog.filter.user')}</span>
        <Select
          value={userId}
          onChange={(v) => {
            setUserId(v);
            setPage(1);
          }}
          placeholder={ts('loginLog.filter.allUsers')}
          allowClear
          style={{ width: 200 }}
          options={userOptions}
        />
        <span style={{ color: '#666' }}>{ts('loginLog.filter.time')}</span>
        <RangePicker
          value={dateRange}
          onChange={(dates) => {
            setDateRange(dates);
            setPage(1);
          }}
          style={{ width: 280 }}
        />
        <Button
          icon={<SearchOutlined />}
          type="primary"
          onClick={() => {
            setPage(1);
            refetch();
          }}
        >
          {tc('action.search')}
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleReset}>
          {tc('action.reset')}
        </Button>
      </Space>

      {/* 日志表格 */}
      <DataTable<LoginLog>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="id"
        pagination={serverPagination({
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showTotal: (total) => tc('pagination.total', { count: total }),
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          }
        })}
        size="small"
        scroll={{ x: 'max-content' }}
        showCard={false}
        searchable={false}
      />
    </Card>
  );
}

export default LoginLogs;
