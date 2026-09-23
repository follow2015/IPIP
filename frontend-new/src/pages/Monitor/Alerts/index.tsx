/**
 * 监控中心 - 告警历史页（P1-4）
 *
 * 查阅全部告警投递记录（设备删除后历史行保留，device 字段置空）。
 * 支持按 alert_type / severity / status / 时间范围过滤，分页浏览；
 * failed 状态的告警可一键重试（乐观锁，仅 failed 行可重置）。
 */
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Tag,
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
import type { Breakpoint } from 'antd';
import DataTable from '@/components/DataTable';
import { useResponsive } from '@/hooks/useResponsive';
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
  type MonitorAlertQuery
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import {
  NotificationTypeCode,
  SEVERITY_COLOR_MAP,
  NOTIFICATION_TYPE_LABEL_KEYS
} from '@/types/enums';
import { getSeverityOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { translateProbeError, formatDateTime, relativeTime } from '@/utils/format';
import { ALERT_TYPE_COLOR } from '@/constants/monitor';
import type { TFunction } from 'i18next';

const { Text } = Typography;
const { RangePicker } = DatePicker;

const alertTypeLabel = (type: string, td: TFunction<'device'>) => {
  const key = NOTIFICATION_TYPE_LABEL_KEYS[type as NotificationTypeCode];
  return key ? td(key) : type;
};

const getAlertTypeOptions = (t: TFunction<'monitor'>, td: TFunction<'device'>) => [
  { label: t('filter.all'), value: '' },
  ...(
    [
      NotificationTypeCode.DEVICE_UNREACHABLE,
      NotificationTypeCode.DEVICE_RECOVERED,
      NotificationTypeCode.TEMPERATURE_ALERT,
      NotificationTypeCode.DISK_FAILURE_ALERT,
      NotificationTypeCode.PORT_STATUS_CHANGED,
      NotificationTypeCode.MONITOR_INTERRUPTED,
      NotificationTypeCode.RAID_FAILURE_ALERT
    ] as NotificationTypeCode[]
  ).map((code) => ({ label: alertTypeLabel(code, td), value: code }))
];

const getStatusOptions = (t: TFunction<'monitor'>) => [
  { label: t('filter.all'), value: '' },
  { label: t('alerts.deliveryStatus.pending'), value: 'pending' },
  { label: t('alerts.deliveryStatus.sent'), value: 'sent' },
  { label: t('alerts.deliveryStatus.failed'), value: 'failed' }
];

const STATUS_COLOR: Record<string, string> = {
  pending: 'gold',
  sent: 'green',
  failed: 'red'
};

export default function MonitorAlerts() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
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
  const ackModal = useDisclosure();
  const [ackTarget, setAckTarget] = useState<MonitorAlertItem | null>(null);
  const [ackNote, setAckNote] = useState('');
  const { isMobile } = useResponsive();

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

  const { data, isLoading, isFetching, refetch } = useMonitorAlerts(query);

  const batch = useBatchSelection<MonitorAlertItem>({
    dataSource: data?.items ?? [],
    getRowKey: (r) => String(r.id)
  });

  const handleBatchAck = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchAckAlert.mutateAsync({ alertIds: ids });
      message.success(
        t('alerts.message.batchAck', { count: res.acknowledged }) +
          (res.not_found
            ? t('alerts.message.notFoundSuffix', { count: res.not_found })
            : '')
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.batchAckFailed'));
    }
  };

  const handleBatchRetry = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchRetryAlert.mutateAsync(ids);
      message.success(
        t('alerts.message.batchRetry', { count: res.retried }) +
          (res.skipped ? t('alerts.message.skipSuffix', { count: res.skipped }) : '')
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.batchRetryFailed'));
    }
  };

  const handleClose = async (item: MonitorAlertItem) => {
    try {
      await closeAlert.mutateAsync({ alertId: item.id });
      message.success(t('alerts.message.closed'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.closeFailed'));
    }
  };

  const handleBatchClose = async () => {
    try {
      const ids = batch.selectedKeys.map(Number);
      const res = await batchCloseAlert.mutateAsync({ alertIds: ids });
      message.success(
        t('alerts.message.batchClose', { count: res.closed }) +
          (res.not_found
            ? t('alerts.message.notFoundSuffix', { count: res.not_found })
            : '')
      );
      batch.clear();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.batchCloseFailed'));
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
        message.success(t('alerts.message.retryQueued'));
      } else {
        message.info(t('alerts.message.retryNotNeeded'));
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.retryFailed'));
    }
  };

  const openAckModal = (item: MonitorAlertItem) => {
    setAckTarget(item);
    setAckNote(item.ack_note ?? '');
    ackModal.open();
  };

  const handleAckSubmit = async () => {
    if (!ackTarget) return;
    try {
      await ackAlert.mutateAsync({ alertId: ackTarget.id, note: ackNote || undefined });
      message.success(t('alerts.message.acknowledgedDone'));
      ackModal.close();
      setAckTarget(null);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.ackFailed'));
    }
  };

  const columns = [
    {
      title: t('column.device'),
      key: 'device',
      render: (_: unknown, record: MonitorAlertItem) => {
        if (record.device_id == null || !record.device_name) {
          return <Text type="secondary">{t('alerts.deletedDevice')}</Text>;
        }
        return <Link to={`/devices/${record.device_id}`}>{record.device_name}</Link>;
      }
    },
    {
      title: tc('field.type'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      responsive: ['md'] satisfies Breakpoint[], // ≥768
      render: (deviceType: string | null) => (deviceType ? <Tag>{deviceType}</Tag> : '-')
    },
    {
      title: t('column.managementIp'),
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      responsive: ['md'] satisfies Breakpoint[], // ≥768
      render: (ip: string | null) => ip || '-'
    },
    {
      title: t('column.alertType'),
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 120,
      render: (alertType: string) => (
        <Tag color={ALERT_TYPE_COLOR[alertType] || 'default'}>
          {alertTypeLabel(alertType, td)}
        </Tag>
      )
    },
    {
      title: t('column.metricInstance'),
      key: 'metric_instance',
      width: 140,
      responsive: ['lg'] satisfies Breakpoint[], // ≥992
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
      title: tc('field.level'),
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (s: string) => <Tag color={SEVERITY_COLOR_MAP[s] || 'default'}>{s}</Tag>
    },
    {
      title: t('column.deliveryStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      responsive: ['sm'] satisfies Breakpoint[], // ≥576
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>
    },
    {
      title: t('column.attempts'),
      dataIndex: 'attempts',
      key: 'attempts',
      width: 90,
      align: 'center' as const,
      responsive: ['lg'] satisfies Breakpoint[], // ≥992
      render: (n: number) => (n > 0 ? <Text type="danger">{n}</Text> : '-')
    },
    {
      title: t('column.alertTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (iso: string | null) => (
        <Tooltip title={relativeTime(iso, tc)}>{formatDateTime(iso)}</Tooltip>
      )
    },
    {
      title: t('column.lastError'),
      dataIndex: 'last_error',
      key: 'last_error',
      ellipsis: true,
      responsive: ['lg'] satisfies Breakpoint[], // ≥992
      render: (e: string | null) =>
        e ? (
          <Text type="danger" ellipsis title={e}>
            {translateProbeError(e, td)}
          </Text>
        ) : (
          '-'
        )
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 180,
      fixed: 'right' as const,
      render: (_: unknown, record: MonitorAlertItem) => renderActions(record)
    }
  ];

  const renderActions = (record: MonitorAlertItem) => (
    <Space size="small" wrap>
      {/* P1-6: 告警详情 */}
      <Button size="small" onClick={() => setDetailId(record.id)}>
        {tc('action.detail')}
      </Button>
      {record.device_id != null && (
        <Tooltip title={t('alerts.viewTrend')}>
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
          {tc('action.retry')}
        </Button>
      )}
      {/* G9: 人工确认/认领 */}
      <Button size="small" icon={<CheckOutlined />} onClick={() => openAckModal(record)}>
        {record.acknowledged_by ? t('alerts.acknowledged') : tc('action.confirm')}
      </Button>
      {/* P2-16: 手动关闭 */}
      {!record.closed_at && (
        <Button
          size="small"
          danger
          onClick={() => handleClose(record)}
          loading={closeAlert.isPending && closeAlert.variables?.alertId === record.id}
        >
          {tc('action.close')}
        </Button>
      )}
    </Space>
  );

  const renderAlertCard = (record: MonitorAlertItem) => (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Space size={4} wrap>
          <Tag color={SEVERITY_COLOR_MAP[record.severity] || 'default'}>{record.severity}</Tag>
          <Tag color={ALERT_TYPE_COLOR[record.alert_type] || 'default'}>
            {alertTypeLabel(record.alert_type, td)}
          </Tag>
          <Tag color={STATUS_COLOR[record.status] || 'default'}>{record.status}</Tag>
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatDateTime(record.created_at)}
        </Text>
      </div>
      <div>
        {record.device_id == null || !record.device_name ? (
          <Text type="secondary">{t('alerts.deletedDevice')}</Text>
        ) : (
          <Link to={`/devices/${record.device_id}`}>{record.device_name}</Link>
        )}
        {record.management_ip && (
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
            {record.management_ip}
          </Text>
        )}
      </div>
      {record.last_error && (
        <Text type="danger" style={{ fontSize: 12 }} ellipsis>
          {translateProbeError(record.last_error, td)}
        </Text>
      )}
      {renderActions(record)}
    </Space>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 过滤栏 */}
      <Card variant="borderless" style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
        {/* 移动端：垂直堆叠 + 控件全宽；桌面端保持原横向 wrap 布局 */}
        <Space
          direction={isMobile ? 'vertical' : 'horizontal'}
          wrap={!isMobile}
          size="middle"
          style={isMobile ? { width: '100%' } : undefined}
        >
          <Select
            style={{ width: isMobile ? '100%' : 160 }}
            value={alertType}
            options={getAlertTypeOptions(t, td)}
            onChange={(v) => {
              setAlertType(v);
              table.setPage(1);
            }}
            placeholder={t('column.alertType')}
          />
          <Select
            style={{ width: isMobile ? '100%' : 140 }}
            value={severity}
            options={[{ label: t('filter.all'), value: '' }, ...getSeverityOptions(td)]}
            onChange={(v) => {
              setSeverity(v);
              table.setPage(1);
            }}
            placeholder={tc('field.severity')}
          />
          <Segmented
            style={{ width: isMobile ? '100%' : undefined }}
            options={getStatusOptions(t)}
            value={status}
            onChange={(v) => {
              setStatus(v as string);
              table.setPage(1);
            }}
          />
          <RangePicker
            style={{ width: isMobile ? '100%' : undefined }}
            value={range}
            onChange={(v) => {
              setRange(v as [Dayjs, Dayjs] | null);
              table.setPage(1);
            }}
            disabledDate={(cur) => cur && cur > dayjs().endOf('day')}
          />
          <Segmented
            style={{ width: isMobile ? '100%' : undefined }}
            options={[
              { label: t('alerts.filter.scopeAll'), value: 'all' },
              { label: t('alerts.filter.scopeMine'), value: 'mine' }
            ]}
            value={scope}
            onChange={(v) => {
              setScope(v as 'all' | 'mine');
              table.setPage(1);
            }}
          />
          {/* P2-10: 聚合视图切换 */}
          <Segmented
            style={{ width: isMobile ? '100%' : undefined }}
            options={[
              { label: t('alerts.view.list'), value: 'list' },
              { label: t('alerts.view.aggregation'), value: 'aggregation' }
            ]}
            value={viewMode}
            onChange={(v) => setViewMode(v as 'list' | 'aggregation')}
          />
          {/* P1-7: 按 metric_key/index_key 过滤 */}
          <Input
            allowClear
            placeholder={t('alerts.filter.metricKey')}
            value={metricKey}
            onChange={(e) => setMetricKey(e.target.value)}
            onPressEnter={() => table.setPage(1)}
            style={{ width: isMobile ? '100%' : 180 }}
          />
          <Input
            allowClear
            placeholder={t('alerts.filter.indexKey')}
            value={indexKey}
            onChange={(e) => setIndexKey(e.target.value)}
            onPressEnter={() => table.setPage(1)}
            style={{ width: isMobile ? '100%' : 180 }}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isFetching}
            block={isMobile}
          >
            {tc('action.refresh')}
          </Button>
          <Button onClick={resetFilters} block={isMobile}>
            {tc('action.reset')}
          </Button>
          {/* G5: 导出告警 CSV */}
          <Button
            icon={<DownloadOutlined />}
            loading={exportAlerts.isPending}
            block={isMobile}
            onClick={async () => {
              try {
                await exportAlerts.mutateAsync(query);
              } catch (err: unknown) {
                message.error(err instanceof Error ? err.message : t('export.failed'));
              }
            }}
          >
            {t('export.csv')}
          </Button>
        </Space>
      </Card>

      {/* 告警历史表格 */}
      <Card
        title={viewMode === 'list' ? t('alerts.title') : t('alerts.aggregationTitle')}
        variant="borderless"
        style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
      >
        {viewMode === 'aggregation' ? (
          <DataTable<MonitorAlertAggregationItem>
            rowKey={(r) => `${r.alert_type}-${r.severity}-${r.device_id ?? 'null'}`}
            dataSource={aggregations.data ?? []}
            loading={aggregations.isLoading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            searchable={false}
            showCard={false}
            columns={[
              {
                title: t('column.alertType'),
                dataIndex: 'alert_type',
                render: (v: string) => <Tag>{v}</Tag>
              },
              {
                title: tc('field.level'),
                dataIndex: 'severity',
                render: (v: string) => <Tag color={SEVERITY_COLOR_MAP[v] ?? 'default'}>{v}</Tag>
              },
              { title: t('column.device'), dataIndex: 'device_name' },
              {
                title: t('column.alertCount'),
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
                title: t('column.firstAt'),
                dataIndex: 'first_at',
                responsive: ['lg'] satisfies Breakpoint[], // ≥992
                render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-')
              },
              {
                title: t('column.lastAt'),
                dataIndex: 'last_at',
                responsive: ['sm'] satisfies Breakpoint[], // ≥576
                render: (v: string) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-')
              },
              {
                title: t('column.sampleIds'),
                dataIndex: 'sample_ids',
                responsive: ['lg'] satisfies Breakpoint[], // ≥992
                render: (ids: number[]) => ids.join(', ')
              }
            ]}
          />
        ) : (
          <>
            <BatchActionBar
              count={batch.count}
              unit={t('stat.unitAlert', { count: batch.count })}
              onClear={batch.clear}
            >
              <Button
                size="small"
                icon={<CheckOutlined />}
                onClick={handleBatchAck}
                loading={batchAckAlert.isPending}
              >
                {t('alerts.batch.ack')}
              </Button>
              <Button
                size="small"
                icon={<RedoOutlined />}
                onClick={handleBatchRetry}
                loading={batchRetryAlert.isPending}
              >
                {t('alerts.batch.retry')}
              </Button>
              <Button
                size="small"
                danger
                onClick={handleBatchClose}
                loading={batchCloseAlert.isPending}
              >
                {t('alerts.batch.close')}
              </Button>
            </BatchActionBar>
            <DataTable<MonitorAlertItem>
              columns={columns}
              dataSource={data?.items ?? []}
              loading={isLoading}
              rowKey={(r) => String(r.id)}
              rowSelection={batch.rowSelection}
              emptyText={t('alerts.empty')}
              total={data?.total ?? 0}
              searchable={false}
              showCard={false}
              tableProps={table}
              mobileCardMode
              cardRender={renderAlertCard}
            />
          </>
        )}
      </Card>

      {/* G9: 确认告警 Modal */}
      <Modal
        title={t('alerts.ackModal.title')}
        open={ackModal.isOpen}
        onOk={handleAckSubmit}
        onCancel={() => {
          ackModal.close();
          setAckTarget(null);
        }}
        confirmLoading={ackAlert.isPending}
        okText={tc('action.confirm')}
        cancelText={tc('action.cancel')}
        width={isMobile ? 'calc(100vw - 32px)' : 520}
      >
        {ackTarget && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Text>
              {t('alerts.ackModal.prompt', {
                id: ackTarget.id,
                type: alertTypeLabel(ackTarget.alert_type, td)
              })}
              {ackTarget.acknowledged_by && (
                <Text type="secondary">
                  {t('alerts.ackModal.acknowledgedBy', { user: ackTarget.acknowledged_by })}
                </Text>
              )}
            </Text>
            <Input.TextArea
              value={ackNote}
              onChange={(e) => setAckNote(e.target.value)}
              placeholder={t('alerts.ackModal.notePlaceholder')}
              maxLength={2000}
              showCount
              autoSize={{ minRows: 3, maxRows: 6 }}
            />
          </Space>
        )}
      </Modal>

      {/* P1-6: 告警详情 Drawer */}
      <Drawer
        title={t('alerts.detail.title')}
        open={detailId != null}
        onClose={() => setDetailId(null)}
        width={isMobile ? '100vw' : 640}
        destroyOnClose
      >
        {detailQuery.isLoading && (
          <Typography.Text type="secondary">{tc('message.loading')}</Typography.Text>
        )}
        {detailQuery.data && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label={t('alerts.detail.id')}>
                {detailQuery.data.id}
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.type')}>
                <Tag color={ALERT_TYPE_COLOR[detailQuery.data.alert_type] || 'default'}>
                  {alertTypeLabel(detailQuery.data.alert_type, td)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.level')}>
                <Tag color={SEVERITY_COLOR_MAP[detailQuery.data.severity] || 'default'}>
                  {detailQuery.data.severity}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.status')}>
                <Tag color={STATUS_COLOR[detailQuery.data.status] || 'default'}>
                  {detailQuery.data.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('column.device')} span={2}>
                {detailQuery.data.device_name ?? (
                  <Typography.Text type="secondary">
                    {t('alerts.detail.deviceDeleted')}
                  </Typography.Text>
                )}
                {detailQuery.data.device_name && (
                  <>
                    {' '}
                    <Typography.Text type="secondary">
                      ({detailQuery.data.device_type} /{' '}
                      {detailQuery.data.management_ip || t('alerts.detail.noIp')})
                    </Typography.Text>
                  </>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('alerts.detail.dedupKey')} span={2}>
                <Typography.Text code copyable style={{ wordBreak: 'break-all' }}>
                  {detailQuery.data.dedup_key}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.createdAt')}>
                {detailQuery.data.created_at ? formatDateTime(detailQuery.data.created_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('alerts.detail.sentAt')}>
                {detailQuery.data.sent_at ? formatDateTime(detailQuery.data.sent_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('alerts.detail.attempts')}>
                {detailQuery.data.attempts}
              </Descriptions.Item>
              <Descriptions.Item label={t('column.lastError')}>
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
            <Descriptions column={1} bordered size="small" title={t('alerts.detail.ackSection')}>
              <Descriptions.Item label={t('alerts.detail.ackBy')}>
                {detailQuery.data.acknowledged_by ?? (
                  <Typography.Text type="secondary">
                    {t('alerts.detail.notAcknowledged')}
                  </Typography.Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('alerts.detail.ackAt')}>
                {detailQuery.data.acknowledged_at
                  ? formatDateTime(detailQuery.data.acknowledged_at)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('alerts.detail.ackNote')}>
                {detailQuery.data.ack_note ?? '-'}
              </Descriptions.Item>
            </Descriptions>

            {/* Payload 解析 */}
            <Descriptions
              column={1}
              bordered
              size="small"
              title={t('alerts.detail.payloadSection')}
            >
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
