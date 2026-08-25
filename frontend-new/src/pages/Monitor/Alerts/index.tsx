/**
 * 监控中心 - 告警历史页（P1-4）
 *
 * 查阅全部告警投递记录（设备删除后历史行保留，device 字段置空）。
 * 支持按 alert_type / severity / status / 时间范围过滤，分页浏览；
 * failed 状态的告警可一键重试（乐观锁，仅 failed 行可重置）。
 */
import { useState } from 'react';
import {
  Card,
  Tag,
  Table,
  Button,
  Space,
  Select,
  Segmented,
  Typography,
  DatePicker,
  Tooltip,
  Modal,
  Drawer,
  Descriptions,
  Input
} from 'antd';
import DataTable from '@/components/DataTable';
import BatchActionBar from '@/components/BatchActionBar/BatchActionBar';
import {
  ReloadOutlined,
  RedoOutlined,
  LineChartOutlined,
  CheckOutlined,
  DownloadOutlined
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { Link, useNavigate } from 'react-router-dom';
import {
  useMonitorAlerts,
  useRetryAlert,
  useAckAlert,
  useBatchRetryAlert,
  useBatchAckAlert,
  useCloseAlert,
  useBatchCloseAlert,
  useAlertDetail,
  useAlertAggregations,
  type MonitorAlertAggregationItem,
  useExportAlerts,
  type MonitorAlertItem,
  type MonitorAlertDetail,
  type MonitorAlertQuery
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import { NotificationTypeCode } from '@/types/status-codes.generated';
import { SEVERITY_OPTIONS, SEVERITY_COLOR_MAP } from '@/types/enums';
import { translateProbeError, formatDateTime, relativeTime } from '@/utils/format';
import { ALERT_TYPE_LABEL, ALERT_TYPE_COLOR } from '@/constants/monitor';

const { Text } = Typography;
const { RangePicker } = DatePicker;

const ALERT_TYPE_OPTIONS = [
  { label: '全部', value: '' },
  { label: '设备不可达', value: NotificationTypeCode.DEVICE_UNREACHABLE },
  { label: '设备恢复', value: NotificationTypeCode.DEVICE_RECOVERED },
  { label: '温度告警', value: NotificationTypeCode.TEMPERATURE_ALERT },
  { label: '硬盘故障', value: NotificationTypeCode.DISK_FAILURE_ALERT },
  { label: '端口状态变化', value: NotificationTypeCode.PORT_STATUS_CHANGED },
  { label: '监控中断', value: NotificationTypeCode.MONITOR_INTERRUPTED },
  { label: 'RAID故障', value: NotificationTypeCode.RAID_FAILURE_ALERT }
];

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待投递', value: 'pending' },
  { label: '已投递', value: 'sent' },
  { label: '失败', value: 'failed' }
];

const STATUS_COLOR: Record<string, string> = {
  pending: 'gold',
  sent: 'green',
  failed: 'red'
};

export default function MonitorAlerts() {
  const message = useMessage();
  const navigate = useNavigate();
  const table = useTable();
  const retryAlert = useRetryAlert();
  const ackAlert = useAckAlert();
  const batchRetryAlert = useBatchRetryAlert();
  const batchAckAlert = useBatchAckAlert();
  const closeAlert = useCloseAlert();
  const batchCloseAlert = useBatchCloseAlert();
  const exportAlerts = useExportAlerts();

  const [viewMode, setViewMode] = useState<'list' | 'aggregation'>('list');

  const [alertType, setAlertType] = useState<string>('');
  const [severity, setSeverity] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const aggregations = useAlertAggregations({
    window_minutes: 5,
    severity: severity || undefined,
    only_active: true,
    max_groups: 50
  });
  const [detailId, setDetailId] = useState<number | null>(null);
  const detailQuery = useAlertDetail(detailId);
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [scope, setScope] = useState<'all' | 'mine'>('all');
  const [metricKey, setMetricKey] = useState<string>('');
  const [indexKey, setIndexKey] = useState<string>('');
  const [ackModalOpen, setAckModalOpen] = useState(false);
  const [ackTarget, setAckTarget] = useState<MonitorAlertItem | null>(null);
  const [ackNote, setAckNote] = useState('');

  const query: MonitorAlertQuery = {
    alert_type: alertType || undefined,
    severity: severity || undefined,
    status: status || undefined,
    start_date: range?.[0]?.toISOString(),
    end_date: range?.[1]?.toISOString(),
    scope,
    metric_key: metricKey || undefined,
    index_key: indexKey || undefined,
    page: table.page,
    per_page: table.perPage
  };

  const { data, isLoading, isFetching } = useMonitorAlerts(query);

  const batch = useBatchSelection<MonitorAlertItem>({
    dataSource: data?.items ?? [],
    getRowKey: (r) => String(r.id)
  });

  const handleBatchAck = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchAckAlert.mutateAsync({ alertIds: ids });
      message.success(
        `已确认 ${res.acknowledged} 条${res.not_found ? `，${res.not_found} 条不存在` : ''}`
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '批量确认失败');
    }
  };

  const handleBatchRetry = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchRetryAlert.mutateAsync(ids);
      message.success(
        `已重试 ${res.retried} 条${res.skipped ? `，${res.skipped} 条非 failed 状态已跳过` : ''}`
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '批量重试失败');
    }
  };

  const handleClose = async (item: MonitorAlertItem) => {
    try {
      await closeAlert.mutateAsync({ alertId: item.id });
      message.success('告警已关闭');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '关闭失败');
    }
  };

  const handleBatchClose = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchCloseAlert.mutateAsync({ alertIds: ids });
      message.success(
        `已关闭 ${res.closed} 条${res.not_found ? `，${res.not_found} 条不存在` : ''}`
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '批量关闭失败');
    }
  };

  const resetFilters = () => {
    setAlertType('');
    setSeverity('');
    setStatus('');
    setRange(null);
    setMetricKey('');
    setIndexKey('');
    table.setPage(1);
  };

  const handleRetry = async (item: MonitorAlertItem) => {
    try {
      const res = await retryAlert.mutateAsync(item.id);
      if (res.retried) {
        message.success('已重新加入投递队列');
      } else {
        message.info('该告警非失败状态，无需重试');
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '重试请求失败');
    }
  };

  const openAckModal = (item: MonitorAlertItem) => {
    setAckTarget(item);
    setAckNote(item.ack_note ?? '');
    setAckModalOpen(true);
  };

  const handleAckSubmit = async () => {
    if (!ackTarget) return;
    try {
      await ackAlert.mutateAsync({ alertId: ackTarget.id, note: ackNote || undefined });
      message.success('已确认告警');
      setAckModalOpen(false);
      setAckTarget(null);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '确认请求失败');
    }
  };

  const columns = [
    {
      title: '设备',
      key: 'device',
      render: (_: unknown, record: MonitorAlertItem) => {
        if (record.device_id == null || !record.device_name) {
          return <Text type="secondary">已删除设备</Text>;
        }
        return <Link to={`/devices/${record.device_id}`}>{record.device_name}</Link>;
      }
    },
    {
      title: '类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (t: string | null) => (t ? <Tag>{t}</Tag> : '-')
    },
    {
      title: '管理IP',
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      render: (ip: string | null) => ip || '-'
    },
    {
      title: '告警类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 120,
      render: (t: string) => (
        <Tag color={ALERT_TYPE_COLOR[t] || 'default'}>{ALERT_TYPE_LABEL[t] || t}</Tag>
      )
    },
    {
      title: '指标实例',
      key: 'metric_instance',
      width: 140,
      render: (_: unknown, record: MonitorAlertItem) => {
        try {
          const parsed = record.payload_json ? JSON.parse(record.payload_json) : null;
          const idx = parsed?.payload?.index;
          if (idx)
            return (
              <Text ellipsis title={String(idx)}>
                {String(idx)}
              </Text>
            );
        } catch {
          /* ignore */
        }
        return '-';
      }
    },
    {
      title: '级别',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (s: string) => <Tag color={SEVERITY_COLOR_MAP[s] || 'default'}>{s}</Tag>
    },
    {
      title: '投递状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>
    },
    {
      title: '重试次数',
      dataIndex: 'attempts',
      key: 'attempts',
      width: 90,
      align: 'center' as const,
      render: (n: number) => (n > 0 ? <Text type="danger">{n}</Text> : '-')
    },
    {
      title: '告警时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (iso: string | null) => (
        <Tooltip title={relativeTime(iso)}>{formatDateTime(iso)}</Tooltip>
      )
    },
    {
      title: '最后错误',
      dataIndex: 'last_error',
      key: 'last_error',
      ellipsis: true,
      render: (e: string | null) =>
        e ? (
          <Text type="danger" ellipsis title={e}>
            {translateProbeError(e)}
          </Text>
        ) : (
          '-'
        )
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right' as const,
      render: (_: unknown, record: MonitorAlertItem) => (
        <Space size="small">
          {/* P1-6: 告警详情 */}
          <Button size="small" onClick={() => setDetailId(record.id)}>
            详情
          </Button>
          {record.device_id != null && (
            <Tooltip title="查看历史趋势">
              <Button
                size="small"
                icon={<LineChartOutlined />}
                onClick={() => navigate(`/monitor/history?deviceId=${record.device_id}`)}
              />
            </Tooltip>
          )}
          {record.status === 'failed' && (
            <Button
              size="small"
              icon={<RedoOutlined />}
              loading={retryAlert.isPending && retryAlert.variables === record.id}
              onClick={() => handleRetry(record)}
            >
              重试
            </Button>
          )}
          {/* G9: 人工确认/认领 */}
          <Button size="small" icon={<CheckOutlined />} onClick={() => openAckModal(record)}>
            {record.acknowledged_by ? '已确认' : '确认'}
          </Button>
          {/* P2-16: 手动关闭 */}
          {!record.closed_at && (
            <Button
              size="small"
              danger
              onClick={() => handleClose(record)}
              loading={closeAlert.isPending && closeAlert.variables?.alertId === record.id}
            >
              关闭
            </Button>
          )}
        </Space>
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 过滤栏 */}
      <Card variant="borderless" style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
        <Space wrap size="middle">
          <Select
            style={{ width: 160 }}
            value={alertType}
            options={ALERT_TYPE_OPTIONS}
            onChange={(v) => {
              setAlertType(v);
              table.setPage(1);
            }}
            placeholder="告警类型"
          />
          <Select
            style={{ width: 140 }}
            value={severity}
            options={[{ label: '全部', value: '' }, ...SEVERITY_OPTIONS]}
            onChange={(v) => {
              setSeverity(v);
              table.setPage(1);
            }}
            placeholder="严重级别"
          />
          <Segmented
            options={STATUS_OPTIONS}
            value={status}
            onChange={(v) => {
              setStatus(v as string);
              table.setPage(1);
            }}
          />
          <RangePicker
            value={range}
            onChange={(v) => {
              setRange(v as [Dayjs, Dayjs] | null);
              table.setPage(1);
            }}
            disabledDate={(cur) => cur && cur > dayjs().endOf('day')}
          />
          <Segmented
            options={[
              { label: '全部可见', value: 'all' },
              { label: '我负责的', value: 'mine' }
            ]}
            value={scope}
            onChange={(v) => {
              setScope(v as 'all' | 'mine');
              table.setPage(1);
            }}
          />
          {/* P2-10: 聚合视图切换 */}
          <Segmented
            options={[
              { label: '列表视图', value: 'list' },
              { label: '聚合视图', value: 'aggregation' }
            ]}
            value={viewMode}
            onChange={(v) => setViewMode(v as 'list' | 'aggregation')}
          />
          {/* P1-7: 按 metric_key/index_key 过滤 */}
          <Input
            allowClear
            placeholder="指标键（metric_key）"
            value={metricKey}
            onChange={(e) => setMetricKey(e.target.value)}
            onPressEnter={() => table.setPage(1)}
            style={{ width: 180 }}
          />
          <Input
            allowClear
            placeholder="实例键（index_key）"
            value={indexKey}
            onChange={(e) => setIndexKey(e.target.value)}
            onPressEnter={() => table.setPage(1)}
            style={{ width: 180 }}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => table.setPage(table.page)}
            loading={isFetching}
          >
            刷新
          </Button>
          <Button onClick={resetFilters}>重置</Button>
          {/* G5: 导出告警 CSV */}
          <Button
            icon={<DownloadOutlined />}
            loading={exportAlerts.isPending}
            onClick={async () => {
              try {
                await exportAlerts.mutateAsync(query);
              } catch (err: unknown) {
                message.error(err instanceof Error ? err.message : '导出失败');
              }
            }}
          >
            导出 CSV
          </Button>
        </Space>
      </Card>

      {/* 告警历史表格 */}
      <Card
        title={viewMode === 'list' ? '告警历史' : '告警聚合（风暴组）'}
        variant="borderless"
        style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
      >
        {viewMode === 'aggregation' ? (
          <Table<MonitorAlertAggregationItem>
            rowKey={(r) => `${r.alert_type}-${r.severity}-${r.device_id ?? 'null'}`}
            dataSource={aggregations.data ?? []}
            loading={aggregations.isLoading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            columns={[
              {
                title: '告警类型',
                dataIndex: 'alert_type',
                render: (v: string) => <Tag>{v}</Tag>
              },
              {
                title: '级别',
                dataIndex: 'severity',
                render: (v: string) => <Tag color={SEVERITY_COLOR_MAP[v] ?? 'default'}>{v}</Tag>
              },
              { title: '设备', dataIndex: 'device_name' },
              {
                title: '告警数',
                dataIndex: 'count',
                render: (v: number) => (
                  <span
                    style={{
                      fontWeight: 600,
                      color: v >= 5 ? '#ff4d4f' : v >= 3 ? '#faad14' : undefined
                    }}
                  >
                    {v}
                  </span>
                ),
                sorter: (a, b) => a.count - b.count,
                defaultSortOrder: 'descend'
              },
              {
                title: '首次',
                dataIndex: 'first_at',
                render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-')
              },
              {
                title: '最近',
                dataIndex: 'last_at',
                render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-')
              },
              {
                title: '样本告警 ID',
                dataIndex: 'sample_ids',
                render: (ids: number[]) => ids.join(', ')
              }
            ]}
          />
        ) : (
          <>
            <BatchActionBar count={batch.count} unit="条告警" onClear={batch.clear}>
              <Button
                size="small"
                icon={<CheckOutlined />}
                onClick={handleBatchAck}
                loading={batchAckAlert.isPending}
              >
                批量确认
              </Button>
              <Button
                size="small"
                icon={<RedoOutlined />}
                onClick={handleBatchRetry}
                loading={batchRetryAlert.isPending}
              >
                批量重试
              </Button>
              <Button
                size="small"
                danger
                onClick={handleBatchClose}
                loading={batchCloseAlert.isPending}
              >
                批量关闭
              </Button>
            </BatchActionBar>
            <DataTable<MonitorAlertItem>
              columns={columns}
              dataSource={data?.items ?? []}
              loading={isLoading}
              rowKey={(r) => String(r.id)}
              rowSelection={batch.rowSelection}
              emptyText="暂无告警记录"
              total={data?.total ?? 0}
              searchable={false}
              showCard={false}
              tableProps={table}
            />
          </>
        )}
      </Card>

      {/* G9: 确认告警 Modal */}
      <Modal
        title="确认告警"
        open={ackModalOpen}
        onOk={handleAckSubmit}
        onCancel={() => {
          setAckModalOpen(false);
          setAckTarget(null);
        }}
        confirmLoading={ackAlert.isPending}
        okText="确认"
        cancelText="取消"
      >
        {ackTarget && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Text>
              确认告警 #{ackTarget.id}（{ackTarget.alert_type}）
              {ackTarget.acknowledged_by && (
                <Text type="secondary"> · 已由 {ackTarget.acknowledged_by} 确认</Text>
              )}
            </Text>
            <Input.TextArea
              value={ackNote}
              onChange={(e) => setAckNote(e.target.value)}
              placeholder="确认备注（可选）"
              maxLength={2000}
              showCount
              autoSize={{ minRows: 3, maxRows: 6 }}
            />
          </Space>
        )}
      </Modal>

      {/* P1-6: 告警详情 Drawer */}
      <Drawer
        title="告警详情"
        open={detailId != null}
        onClose={() => setDetailId(null)}
        width={640}
        destroyOnClose
      >
        {detailQuery.isLoading && <Typography.Text type="secondary">加载中…</Typography.Text>}
        {detailQuery.data && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="告警ID">{detailQuery.data.id}</Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={ALERT_TYPE_COLOR[detailQuery.data.alert_type] || 'default'}>
                  {ALERT_TYPE_LABEL[detailQuery.data.alert_type] || detailQuery.data.alert_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="级别">
                <Tag color={SEVERITY_COLOR_MAP[detailQuery.data.severity] || 'default'}>
                  {detailQuery.data.severity}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[detailQuery.data.status] || 'default'}>
                  {detailQuery.data.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="设备" span={2}>
                {detailQuery.data.device_name ?? (
                  <Typography.Text type="secondary">已删除</Typography.Text>
                )}
                {detailQuery.data.device_name && (
                  <>
                    {' '}
                    <Typography.Text type="secondary">
                      ({detailQuery.data.device_type} / {detailQuery.data.management_ip || '无IP'})
                    </Typography.Text>
                  </>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="去重键" span={2}>
                <Typography.Text code copyable style={{ wordBreak: 'break-all' }}>
                  {detailQuery.data.dedup_key}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {detailQuery.data.created_at
                  ? dayjs(detailQuery.data.created_at).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="发送时间">
                {detailQuery.data.sent_at
                  ? dayjs(detailQuery.data.sent_at).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="尝试次数">{detailQuery.data.attempts}</Descriptions.Item>
              <Descriptions.Item label="最后错误">
                {detailQuery.data.last_error ? (
                  <Typography.Text type="danger" style={{ wordBreak: 'break-all' }}>
                    {detailQuery.data.last_error}
                  </Typography.Text>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
            </Descriptions>

            {/* 确认信息 */}
            <Descriptions column={1} bordered size="small" title="确认信息">
              <Descriptions.Item label="确认人">
                {detailQuery.data.acknowledged_by ?? (
                  <Typography.Text type="secondary">未确认</Typography.Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="确认时间">
                {detailQuery.data.acknowledged_at
                  ? dayjs(detailQuery.data.acknowledged_at).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="确认备注">
                {detailQuery.data.ack_note ?? '-'}
              </Descriptions.Item>
            </Descriptions>

            {/* Payload 解析 */}
            <Descriptions column={1} bordered size="small" title="告警载荷">
              <Descriptions.Item label="payload">
                <pre style={{ margin: 0, maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
                  {JSON.stringify(detailQuery.data.payload, null, 2)}
                </pre>
              </Descriptions.Item>
            </Descriptions>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
