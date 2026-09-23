import { useState } from 'react';
import {
  Card,
  Tag,
  Space,
  Select,
  Button,
  Drawer,
  Descriptions,
  Typography,
  Tooltip,
  Input
} from 'antd';
import DataTable from '@/components/DataTable';
import { serverPagination } from '@/components/DataTable/serverPagination';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  useIncidents,
  useIncidentDetail,
  type IncidentItem,
  type IncidentListParams
} from '@/services/monitor';
import { formatDateTime } from '@/utils/format';
import { useResponsive } from '@/hooks/useResponsive';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const { Text } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  info: 'blue'
};

type IncidentReasonCode = 'L1_rule' | 'L2_topology' | 'L2_manual_rule' | 'L3_change';
type IncidentReasonKey =
  | 'incident.reason.L1_rule'
  | 'incident.reason.L2_topology'
  | 'incident.reason.L2_manual_rule'
  | 'incident.reason.L3_change';
const REASON_LABEL_KEYS: Record<IncidentReasonCode, IncidentReasonKey> = {
  L1_rule: 'incident.reason.L1_rule',
  L2_topology: 'incident.reason.L2_topology',
  L2_manual_rule: 'incident.reason.L2_manual_rule',
  L3_change: 'incident.reason.L3_change'
};
const reasonLabel = (code: string | null, t: TFunction<'monitor'>): string | null => {
  if (!code) return null;
  const key = REASON_LABEL_KEYS[code as IncidentReasonCode];
  return key ? t(key) : code;
};

const STATUS_COLOR: Record<string, string> = {
  active: 'processing',
  acknowledged: 'warning',
  closed: 'default'
};

function renderDeviceRef(id: number | null, name: string | null) {
  if (!name) return id != null ? String(id) : '-';
  if (id != null) return name;
  return (
    <Space size={4}>
      <span>{name}</span>
      <Tooltip title="设备已被彻底删除；本行由设备名快照保留（引用列已置空）">
        <Tag color="default" style={{ marginInlineEnd: 0 }}>
          已删除
        </Tag>
      </Tooltip>
    </Space>
  );
}

export default function MonitorIncidents() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const [params, setParams] = useState<IncidentListParams>({
    page: 1,
    per_page: 20
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [deviceNameInput, setDeviceNameInput] = useState('');

  const { data, isLoading, refetch, isFetching } = useIncidents(params);
  const { data: detail, isLoading: detailLoading } = useIncidentDetail(selectedId);

  const items = (data?.items ?? []) as IncidentItem[];
  const total = data?.total ?? 0;

  const { isMobile } = useResponsive();

  const submitDeviceName = (value: string) => {
    const next = value.trim();
    setDeviceNameInput(value);
    setParams((p) => ({ ...p, device_name: next || undefined, page: 1 }));
  };

  const columns: ColumnsType<IncidentItem> = [
    {
      title: t('incident.column.title'),
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, row) => (
        <Tooltip title={title}>
          <a onClick={() => setSelectedId(row.id)}>{title}</a>
        </Tooltip>
      )
    },
    {
      title: tc('field.severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (s: string) => <Tag color={SEVERITY_COLOR[s] ?? 'default'}>{s}</Tag>
    },
    {
      title: tc('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] ?? 'default'}>{s}</Tag>
    },
    {
      title: t('column.alertCount'),
      dataIndex: 'alert_count',
      key: 'alert_count',
      width: 80,
      align: 'right',
      responsive: ['sm'] // ≥576
    },
    {
      responsive: ['md'], // ≥768
      title: t('incident.column.deviceCount'),
      dataIndex: 'device_count',
      key: 'device_count',
      width: 100,
      align: 'right',
      render: (n: number) => (
        <Text strong style={{ color: n > 1 ? '#cf1322' : undefined }}>
          {n}
        </Text>
      )
    },
    {
      responsive: ['lg'], // ≥992
      title: t('incident.column.reasonCode'),
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 120,
      render: (r: string | null) => reasonLabel(r, t) ?? '-'
    },
    {
      title: t('incident.column.firstAlertAt'),
      dataIndex: 'first_alert_at',
      key: 'first_alert_at',
      width: 160,
      render: (v: string | null) => (v ? formatDateTime(v) : '-')
    },
    {
      responsive: ['md'], // ≥768
      title: t('incident.column.lastAlertAt'),
      dataIndex: 'last_alert_at',
      key: 'last_alert_at',
      width: 160,
      render: (v: string | null) => (v ? formatDateTime(v) : '-')
    }
  ];

  const renderIncidentCard = (row: IncidentItem) => (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      {/* inline-block + padding 撑出 ≥32px 触摸区域：裸 <a> 行内盒高度不足，窄屏难以点中 */}
      <a
        onClick={() => setSelectedId(row.id)}
        style={{ fontWeight: 500, display: 'inline-block', padding: '6px 0', minHeight: 32 }}
      >
        {row.title}
      </a>
      <Space size={4} wrap>
        <Tag color={SEVERITY_COLOR[row.severity] ?? 'default'}>{row.severity}</Tag>
        <Tag color={STATUS_COLOR[row.status] ?? 'default'}>{row.status}</Tag>
        {row.reason_code && <Tag>{reasonLabel(row.reason_code, t)}</Tag>}
      </Space>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {t('incident.cardSummary', { alerts: row.alert_count, devices: row.device_count })}
      </Text>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {t('incident.cardTime', {
          first: row.first_alert_at ? formatDateTime(row.first_alert_at) : '-',
          last: row.last_alert_at ? formatDateTime(row.last_alert_at) : '-'
        })}
      </Text>
    </Space>
  );

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined />
          <span>{t('incident.title')}</span>
        </Space>
      }
      extra={
        <Space wrap>
          {/* 服务端检索（子串、不区分大小写）：走 device_name 查询参数，命中
              设备名快照 —— 设备被彻底删除后按 ID 已查不到，只能按名字回溯。
              刻意不用 DataTable 自带的 searchable：那是**客户端**过滤，只会筛
              当前一页（服务端分页下表现为"明明有却搜不到"），故本页保持
              searchable={false}。 */}
          <Input.Search
            allowClear
            placeholder="按设备名搜历史事件"
            style={{ width: isMobile ? '100%' : 220 }}
            value={deviceNameInput}
            onChange={(e) => setDeviceNameInput(e.target.value)}
            onSearch={submitDeviceName}
          />
          <Select
            allowClear
            placeholder={t('incident.filter.status')}
            style={{ width: 140 }}
            value={params.status}
            onChange={(v) => setParams((p) => ({ ...p, status: v || undefined, page: 1 }))}
            options={[
              { value: 'active', label: t('incident.status.active') },
              { value: 'acknowledged', label: t('alerts.acknowledged') },
              { value: 'closed', label: t('incident.status.closed') }
            ]}
          />
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
            {tc('action.refresh')}
          </Button>
        </Space>
      }
    >
      <DataTable<IncidentItem>
        searchable={false}
        showCard={false}
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={isLoading}
        pagination={serverPagination({
          current: params.page,
          pageSize: params.per_page,
          total: total,
          showTotal: false,
          onChange: (page, per_page) => setParams((p) => ({ ...p, page, per_page }))
        })}
        onRow={(row) => ({ onClick: () => setSelectedId(row.id) })}
        mobileCardMode
        cardRender={renderIncidentCard}
      />

      <Drawer
        title={t('incident.detailTitle')}
        open={selectedId != null}
        onClose={() => setSelectedId(null)}
        width={isMobile ? '100vw' : 680}
        loading={detailLoading}
      >
        {detail && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {/* 统一为响应式列数配置，避免 JS 分支与 antd 断点两套语义并存 */}
            <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label={t('incident.column.title')} span={2}>
                {detail.title}
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.severity')}>
                <Tag color={SEVERITY_COLOR[detail.severity] ?? 'default'}>{detail.severity}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.status')}>
                <Tag color={STATUS_COLOR[detail.status] ?? 'default'}>{detail.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('column.alertCount')}>{detail.alert_count}</Descriptions.Item>
              <Descriptions.Item label={t('incident.column.deviceCount')}>
                <Text strong style={{ color: detail.device_count > 1 ? '#cf1322' : undefined }}>
                  {detail.device_count}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('incident.column.reasonCode')}>
                {reasonLabel(detail.reason_code, t) ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('incident.detail.rootDevice')}>
                {renderDeviceRef(detail.root_device_id, detail.root_device_name)}
              </Descriptions.Item>
              <Descriptions.Item label={t('incident.column.firstAlertAt')}>
                {detail.first_alert_at ? formatDateTime(detail.first_alert_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('incident.column.lastAlertAt')}>
                {detail.last_alert_at ? formatDateTime(detail.last_alert_at) : '-'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title={t('incident.detail.relatedAlerts', { count: detail.related_alerts.length })}>
              <DataTable
                searchable={false}
                showCard={false}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 5 }}
                dataSource={detail.related_alerts}
                columns={[
                  { title: t('incident.column.id'), dataIndex: 'id', width: 70 },
                  { title: tc('field.type'), dataIndex: 'alert_type', width: 140 },
                  { title: tc('field.severity'), dataIndex: 'severity', width: 90 },
                  {
                    title: tc('field.time'),
                    dataIndex: 'created_at',
                    render: (v: string | null) => (v ? formatDateTime(v) : '-')
                  }
                ]}
              />
            </Card>

            <Card
              size="small"
              title={t('incident.detail.suppressedDevices', { count: detail.suppressed_logs.length })}
            >
              <DataTable
                searchable={false}
                showCard={false}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 5 }}
                dataSource={detail.suppressed_logs}
                columns={[
                  {
                    title: t('thresholdOverride.column.deviceId'),
                    dataIndex: 'device_name',
                    width: 160,
                    render: (_: string | null, r) => renderDeviceRef(r.device_id, r.device_name)
                  },
                  { title: t('column.alertType'), dataIndex: 'alert_type', width: 140 },
                  { title: tc('field.severity'), dataIndex: 'severity', width: 90 },
                  {
                    title: t('incident.column.upstreamDevice'),
                    dataIndex: 'upstream_device_name',
                    width: 160,
                    render: (_: string | null, r) =>
                      renderDeviceRef(r.upstream_device_id, r.upstream_device_name)
                  },
                  {
                    title: tc('field.time'),
                    dataIndex: 'created_at',
                    render: (v: string | null) => (v ? formatDateTime(v) : '-')
                  }
                ]}
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </Card>
  );
}
