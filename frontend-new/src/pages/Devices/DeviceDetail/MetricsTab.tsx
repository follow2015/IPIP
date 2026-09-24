/**
 * 设备详情 - 监控数据 Tab
 *
 * 卡片式布局（对齐 CredentialTab / AssetTab 风格），整体标题为「监控数据」：
 * 1. 设备未关联任何凭据 → 整体不展示任何区域，仅提示「需要关联凭据」。
 * 2. 设备关联了 Zabbix 凭据 → 上半部分展示 Zabbix 端口流量（TrafficChart）。
 * 3. 下半部分展示监控指标信息：
 *    - 优先按设备关联的指标模板（组）展示（useDeviceMetricDashboard.grouped=true）；
 *    - 若模板无指标（grouped=false）则沿用现有默认 METRIC_GROUPS 规则 + 活跃告警；
 *    - 有数据且无告警 → 显示「正常」；不可达 / 凭据错误 / 无数据 / 未探测 → 在指标区域
 *      直接展示对应状态（不渲染历史 latest 值，避免误导）；所有监控指标卡片均以灰色呈现。
 *
 * 数据来源：
 * - useDeviceMetricDashboard（凭据/Zabbix/模板组命中/指标状态聚合 + overall_status）
 * - useDeviceMetricAlerts（活跃指标告警，grouped=false 时按默认分组展示）
 * - useDeviceTrafficPorts（Zabbix 端口列表 + configured 标记）
 */
import { Card, Table, Tag, Empty, Spin, Alert, Row, Col, Space, Typography } from 'antd';
import DataTable from '@/components/DataTable';
import {
  FireOutlined,
  SwapOutlined,
  HddOutlined,
  DatabaseOutlined,
  DisconnectOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  LockOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import {
  useDeviceMetricAlerts,
  useDeviceMetricDashboard,
  useDeviceTrafficPorts,
  type DeviceMetricDashboardItem,
  type MonitorStatusCode
} from '@/services/monitor';
import { ErrorBoundary } from '@/components/ErrorBoundary/ErrorBoundary';
import TrafficChart from '@/components/Monitor/TrafficChart';
import { formatDateTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';

type MetricGroupLabelKey =
  | 'group.temperature'
  | 'group.portStatus'
  | 'group.ifInErrors'
  | 'group.ifOutErrors'
  | 'group.ifInDiscards'
  | 'group.ifOutDiscards'
  | 'group.ifUtilization'
  | 'group.cpuUsage'
  | 'group.memoryUsage'
  | 'group.sysUptime'
  | 'group.fanSpeed'
  | 'group.zabbixCpuUsage'
  | 'group.zabbixMemoryUsage'
  | 'group.zabbixTemperature'
  | 'group.zabbixSysUptime'
  | 'group.zabbixIfInErrors'
  | 'group.zabbixIfOutErrors'
  | 'group.zabbixIfInDiscards'
  | 'group.zabbixIfOutDiscards'
  | 'group.raidFailure'
  | 'group.diskFailure'
  | 'group.monitorInterrupted';

interface MetricGroupDef {
  key: string;
  labelKey: MetricGroupLabelKey;
  icon: React.ReactNode;
  protocols?: string[];
}

const METRIC_GROUPS: MetricGroupDef[] = [
  {
    key: 'temperature',
    labelKey: 'group.temperature',
    icon: <FireOutlined />,
    protocols: ['snmp', 'ipmi', 'zabbix']
  },
  { key: 'port_updown', labelKey: 'group.portStatus', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_status', labelKey: 'group.portStatus', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_in_errors', labelKey: 'group.ifInErrors', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_out_errors', labelKey: 'group.ifOutErrors', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_in_discards', labelKey: 'group.ifInDiscards', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_out_discards', labelKey: 'group.ifOutDiscards', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_utilization', labelKey: 'group.ifUtilization', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'cpu_usage', labelKey: 'group.cpuUsage', icon: <ApiOutlined />, protocols: ['snmp', 'zabbix'] },
  {
    key: 'memory_usage',
    labelKey: 'group.memoryUsage',
    icon: <DatabaseOutlined />,
    protocols: ['snmp', 'zabbix']
  },
  {
    key: 'sys_uptime',
    labelKey: 'group.sysUptime',
    icon: <CheckCircleOutlined />,
    protocols: ['snmp', 'zabbix']
  },
  {
    key: 'fan_speed',
    labelKey: 'group.fanSpeed',
    icon: <ApiOutlined />,
    protocols: ['snmp', 'ipmi', 'zabbix']
  },
  {
    key: 'zabbix_cpu_usage',
    labelKey: 'group.zabbixCpuUsage',
    icon: <ApiOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_memory_usage',
    labelKey: 'group.zabbixMemoryUsage',
    icon: <DatabaseOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_temperature',
    labelKey: 'group.zabbixTemperature',
    icon: <FireOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_sys_uptime',
    labelKey: 'group.zabbixSysUptime',
    icon: <CheckCircleOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_in_errors',
    labelKey: 'group.zabbixIfInErrors',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_out_errors',
    labelKey: 'group.zabbixIfOutErrors',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_in_discards',
    labelKey: 'group.zabbixIfInDiscards',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_out_discards',
    labelKey: 'group.zabbixIfOutDiscards',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  { key: 'raid_failure', labelKey: 'group.raidFailure', icon: <DatabaseOutlined />, protocols: ['ipmi'] },
  { key: 'disk_failure', labelKey: 'group.diskFailure', icon: <HddOutlined />, protocols: ['ipmi'] },
  { key: 'monitor_interrupted', labelKey: 'group.monitorInterrupted', icon: <DisconnectOutlined /> }
];

const SEVERITY_COLOR: Record<string, string> = {
  crit: 'red',
  critical: 'red',
  warn: 'orange',
  warning: 'orange',
  info: 'blue',
  ok: 'green'
};

type MetricTagKey =
  | 'metric.severity.critical'
  | 'metric.severity.warning'
  | 'metric.severity.info'
  | 'metric.status.normal'
  | 'metric.column.alert';

const SEVERITY_LABEL_KEY: Record<string, MetricTagKey> = {
  crit: 'metric.severity.critical',
  critical: 'metric.severity.critical',
  warn: 'metric.severity.warning',
  warning: 'metric.severity.warning',
  info: 'metric.severity.info',
  ok: 'metric.status.normal'
};

type MetricOverallKey =
  | 'overall.noCredential'
  | 'overall.notProbed'
  | 'overall.unreachable'
  | 'overall.credentialError'
  | 'overall.noData'
  | 'overall.breached'
  | 'overall.normal';

const OVERALL_STATUS_META: Record<
  string,
  { textKey: MetricOverallKey; type: 'error' | 'warning' | 'info' | 'success'; icon: React.ReactNode }
> = {
  no_credential: { textKey: 'overall.noCredential', type: 'warning', icon: <LockOutlined /> },
  not_probed: { textKey: 'overall.notProbed', type: 'info', icon: <ClockCircleOutlined /> },
  unreachable: {
    textKey: 'overall.unreachable',
    type: 'error',
    icon: <CloseCircleOutlined />
  },
  credential_error: {
    textKey: 'overall.credentialError',
    type: 'warning',
    icon: <WarningOutlined />
  },
  no_data: { textKey: 'overall.noData', type: 'info', icon: <ClockCircleOutlined /> },
  breached: { textKey: 'overall.breached', type: 'warning', icon: <WarningOutlined /> },
  normal: { textKey: 'overall.normal', type: 'success', icon: <CheckCircleOutlined /> }
};

const STATUS_ONLY_OVERALL = new Set(['unreachable', 'credential_error', 'no_data', 'not_probed']);

const MONITOR_STATUS_CODES: readonly MonitorStatusCode[] = [
  'no_credential',
  'not_probed',
  'credential_error',
  'unreachable',
  'normal',
  'normal_no_group',
  'no_data',
  'no_data_template',
  'breached'
];

function isMonitorStatusCode(value: unknown): value is MonitorStatusCode {
  return MONITOR_STATUS_CODES.includes(value as MonitorStatusCode);
}

interface MetricsTabProps {
  deviceId: number;
}

export default function MetricsTab({ deviceId }: MetricsTabProps) {
  const { t } = useTranslation('device');
  const { data: dashboard, isLoading: dashboardLoading } = useDeviceMetricDashboard(deviceId);
  const { data: alertData, isLoading: alertsLoading } = useDeviceMetricAlerts(deviceId);
  const { data: trafficPortsData, isLoading: trafficPortsLoading } =
    useDeviceTrafficPorts(deviceId);

  if (dashboardLoading || alertsLoading || trafficPortsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin />
      </div>
    );
  }

  if (!dashboard?.has_credential) {
    return (
      <Card size="small" title={t('metric.title')}>
        <Empty
          image={<LockOutlined style={{ fontSize: 40, color: '#bbb' }} />}
          description={
            <Space direction="vertical" size={4} style={{ alignItems: 'center' }}>
              <Typography.Text strong>{t('metric.needCredential')}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('metric.needCredentialHint')}
              </Typography.Text>
            </Space>
          }
        />
      </Card>
    );
  }

  const showTraffic = !trafficPortsLoading && !!trafficPortsData?.configured;
  const grouped = dashboard?.grouped ?? false;
  const metricStatus = dashboard?.metric_status ?? [];
  const overall = dashboard?.overall_status ?? 'no_data';
  const overallMeta = OVERALL_STATUS_META[overall] ?? OVERALL_STATUS_META.no_data;
  const statusCode = dashboard?.monitor_status_code;
  const statusReason = isMonitorStatusCode(statusCode)
    ? t(`monitorStatus.${statusCode}`)
    : (dashboard?.status_reason ?? t(`metric.${overallMeta.textKey}`));

  const items = alertData?.items ?? [];
  const groupedAlerts = new Map<string, typeof items>();
  for (const item of items) {
    const list = groupedAlerts.get(item.metric_key) ?? [];
    list.push(item);
    groupedAlerts.set(item.metric_key, list);
  }
  const configuredProtocols = dashboard?.configured_protocols ?? [];
  const hasCredentials = configuredProtocols.length > 0;
  const visibleGroups = hasCredentials
    ? METRIC_GROUPS.filter((g) => {
        if (!g.protocols) return true;
        return g.protocols.some((p) => configuredProtocols.includes(p));
      })
    : [];

  const isStatusOnly = STATUS_ONLY_OVERALL.has(overall);

  const renderMetricStatusTag = (r: DeviceMetricDashboardItem) =>
    r.breached ? (
      <Tag color={SEVERITY_COLOR[r.severity ?? ''] ?? 'orange'}>
        {t(SEVERITY_LABEL_KEY[r.severity ?? ''] ?? 'metric.column.alert')}
      </Tag>
    ) : r.value != null ? (
      <Tag color="green">{t('metric.status.normal')}</Tag>
    ) : (
      <Tag color="default">{t('metric.status.noData')}</Tag>
    );

  const renderMetricCard = (r: DeviceMetricDashboardItem) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Space size={8} wrap>
        <span style={{ fontWeight: 500 }}>{r.metric_name || r.metric_key}</span>
        {renderMetricStatusTag(r)}
      </Space>
      <div style={{ fontSize: 12, color: '#666' }}>
        {t('metric.column.value')}: {r.value ?? '—'} · {r.source ? r.source.toUpperCase() : '—'}
      </div>
      <div style={{ fontSize: 12, color: '#999' }}>
        {r.collected_at ? formatDateTime(r.collected_at) : '—'}
      </div>
    </div>
  );

  return (
    <Card size="small" title={t('metric.title')}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* ── 上半部分：Zabbix 端口流量（仅关联 Zabbix 凭据时显示） ── */}
        {showTraffic && (
          <ErrorBoundary
            fallback={() => (
              <Card size="small" title={t('metric.trafficTitle')}>
                <div>{t('metric.trafficLoadFailed')}</div>
              </Card>
            )}
          >
            <TrafficChart deviceId={deviceId} />
          </ErrorBoundary>
        )}

        {/* ── 下半部分：监控指标信息 ── */}
        <div>
          <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
            <Typography.Text strong>{t('metric.sectionTitle')}</Typography.Text>
            {dashboard?.template_group && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('metric.templateGroup', { name: dashboard.template_group.name })}
              </Typography.Text>
            )}
          </Space>

          {/* 整体状态提示 */}
          <Alert
            type={overallMeta.type}
            showIcon
            icon={overallMeta.icon}
            message={statusReason}
            style={{ marginBottom: 12 }}
          />

          {isStatusOnly ? (
            /* 不可达 / 凭据错误 / 无数据 / 未探测 → 指标区域直接展示对应状态（灰色卡片） */
            <Card size="small" style={{ background: '#fafafa', borderColor: '#d9d9d9' }}>
              <div style={{ textAlign: 'center', padding: 24 }}>
                <Space direction="vertical" size={8} style={{ alignItems: 'center' }}>
                  <span style={{ fontSize: 32, color: '#999' }}>{overallMeta.icon}</span>
                  <Typography.Text type="secondary" strong>
                    {statusReason}
                  </Typography.Text>
                  {overall === 'unreachable' && dashboard?.last_error && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {t('metric.lastError', { error: dashboard.last_error })}
                    </Typography.Text>
                  )}
                  {overall === 'credential_error' && dashboard?.last_error && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {t('metric.lastError', { error: dashboard.last_error })}
                    </Typography.Text>
                  )}
                  {dashboard?.last_checked_at && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {t('metric.lastChecked', { time: formatDateTime(dashboard.last_checked_at) })}
                    </Typography.Text>
                  )}
                </Space>
              </div>
            </Card>
          ) : grouped ? (
            /* 命中模板组且可展示指标 → 按模板指标表格展示（灰色卡片） */
            metricStatus.length > 0 ? (
              <Card
                size="small"
                style={{ background: '#fafafa', borderColor: '#d9d9d9' }}
                styles={{ body: { padding: 0 } }}
              >
                <DataTable<DeviceMetricDashboardItem>
                  dataSource={metricStatus}
                  rowKey="metric_key"
                  size="small"
                  pagination={false}
                  searchable={false}
                  showCard={false}
                  mobileCardMode
                  cardRender={renderMetricCard}
                  columns={[
                    {
                      title: t('metric.column.name'),
                      dataIndex: 'metric_name',
                      render: (v: string, r) => r.metric_name || r.metric_key
                    },
                    {
                      title: t('metric.column.source'),
                      dataIndex: 'source',
                      width: 90,
                      render: (v: string | null) => (v ? v.toUpperCase() : '—')
                    },
                    {
                      title: t('metric.column.value'),
                      dataIndex: 'value',
                      width: 110,
                      render: (v: string | null) => v ?? '—'
                    },
                    {
                      title: t('metric.column.status'),
                      key: 'status',
                      width: 100,
                      render: (_: unknown, r: DeviceMetricDashboardItem) =>
                        r.breached ? (
                          <Tag color={SEVERITY_COLOR[r.severity ?? ''] ?? 'orange'}>
                            {t(SEVERITY_LABEL_KEY[r.severity ?? ''] ?? 'metric.column.alert')}
                          </Tag>
                        ) : r.value != null ? (
                          <Tag color="green">{t('metric.status.normal')}</Tag>
                        ) : (
                          <Tag color="default">{t('metric.status.noData')}</Tag>
                        )
                    },
                    {
                      title: t('metric.column.collectedAt'),
                      dataIndex: 'collected_at',
                      width: 160,
                      render: (v: string | null) => (v ? formatDateTime(v) : '—')
                    }
                  ]}
                  scroll={{ x: 'max-content' }}
                />
              </Card>
            ) : (
              <Empty description={t('metric.emptyGroup')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )
          ) : /* 未命中模板组 → 优先用 latest 数值表格；无 latest 时回退默认分组 + 告警卡片 */
          metricStatus.length > 0 ? (
            <Card
              size="small"
              style={{ background: '#fafafa', borderColor: '#d9d9d9' }}
              styles={{ body: { padding: 0 } }}
            >
              <DataTable<DeviceMetricDashboardItem>
                dataSource={metricStatus}
                rowKey="metric_key"
                size="small"
                pagination={false}
                searchable={false}
                showCard={false}
                mobileCardMode
                cardRender={renderMetricCard}
                columns={[
                  {
                    title: t('metric.column.name'),
                    dataIndex: 'metric_name',
                    render: (v: string, r) => r.metric_name || r.metric_key
                  },
                  {
                    title: t('metric.column.source'),
                    dataIndex: 'source',
                    width: 90,
                    render: (v: string | null) => (v ? v.toUpperCase() : '—')
                  },
                  {
                    title: t('metric.column.value'),
                    dataIndex: 'value',
                    width: 110,
                    render: (v: string | null) => v ?? '—'
                  },
                  {
                    title: t('metric.column.status'),
                    key: 'status',
                    width: 100,
                    render: (_: unknown, r: DeviceMetricDashboardItem) =>
                      r.breached ? (
                        <Tag color={SEVERITY_COLOR[r.severity ?? ''] ?? 'orange'}>
                          {t(SEVERITY_LABEL_KEY[r.severity ?? ''] ?? 'metric.column.alert')}
                        </Tag>
                      ) : r.value != null ? (
                        <Tag color="green">{t('metric.status.normal')}</Tag>
                      ) : (
                        <Tag color="default">{t('metric.status.noData')}</Tag>
                      )
                  },
                  {
                    title: t('metric.column.collectedAt'),
                    dataIndex: 'collected_at',
                    width: 160,
                    render: (v: string | null) => (v ? formatDateTime(v) : '—')
                  }
                ]}
                scroll={{ x: 'max-content' }}
              />
            </Card>
          ) : (
            <>
              {items.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message={t('metric.activeAlertCount', { count: items.length })}
                  style={{ marginBottom: 12 }}
                />
              )}
              <Row gutter={[16, 16]}>
                {visibleGroups.map((group) => {
                  const groupItems = groupedAlerts.get(group.key) ?? [];
                  const hasAlert = groupItems.length > 0;
                  const notProbedYet = hasCredentials && dashboard?.overall_status === 'not_probed';
                  return (
                    <Col xs={24} md={12} key={group.key}>
                      {/* 所有指标卡片灰色呈现 */}
                      <Card
                        size="small"
                        title={
                          <span>
                            {group.icon}
                            <span style={{ marginLeft: 8 }}>{t(`metric.${group.labelKey}`)}</span>
                            {hasAlert && (
                              <Tag
                                color={SEVERITY_COLOR[groupItems[0]?.severity ?? ''] ?? 'orange'}
                                style={{ marginLeft: 8 }}
                              >
                                {t('metric.groupAlertCount', { count: groupItems.length })}
                              </Tag>
                            )}
                          </span>
                        }
                        style={{ background: '#fafafa', borderColor: '#d9d9d9' }}
                      >
                        {group.key === 'monitor_interrupted' ? (
                          hasAlert ? (
                            <Tag color="orange">{t('metric.status.interrupted')}</Tag>
                          ) : notProbedYet ? (
                            <Tag color="default">{t('metric.status.waitingProbe')}</Tag>
                          ) : (
                            <Tag color="green">{t('metric.status.normal')}</Tag>
                          )
                        ) : groupItems.length > 0 ? (
                          <Table
                            dataSource={groupItems}
                            rowKey="id"
                            size="small"
                            pagination={false}
                            columns={[
                              {
                                title: t('metric.column.instance'),
                                dataIndex: 'index_key',
                                render: (v: string) => v || '—',
                                ellipsis: true
                              },
                              {
                                title: t('metric.column.severity'),
                                dataIndex: 'severity',
                                width: 70,
                                render: (sev: string | null) => (
                                  <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>
                                    {SEVERITY_LABEL_KEY[sev ?? ''] ? t(SEVERITY_LABEL_KEY[sev ?? '']) : sev ?? '—'}
                                  </Tag>
                                )
                              },
                              {
                                title: t('metric.column.value'),
                                dataIndex: 'last_value',
                                width: 80,
                                render: (v: string | null) => v ?? '—'
                              }
                            ]}
                            scroll={{ x: 'max-content' }}
                          />
                        ) : notProbedYet ? (
                          <Tag color="default">{t('metric.status.waitingProbe')}</Tag>
                        ) : (
                          <Tag color="green">{t('metric.status.normal')}</Tag>
                        )}
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            </>
          )}
        </div>

        {/* ── 活跃告警明细区域（有告警才显示） ── */}
        {items.length > 0 && (
          <div>
            <Space style={{ marginBottom: 8 }}>
              <WarningOutlined style={{ color: '#fa8c16' }} />
              <Typography.Text strong>{t('metric.activeAlertDetail')}</Typography.Text>
              <Tag color="orange">{t('metric.itemCount', { count: items.length })}</Tag>
            </Space>
            <Card
              size="small"
              style={{ background: '#fff7e6', borderColor: '#ffd591' }}
              styles={{ body: { padding: 0 } }}
            >
              <Table
                dataSource={items}
                rowKey="id"
                size="small"
                pagination={items.length > 10 ? { pageSize: 10, size: 'small' } : false}
                columns={[
                  {
                    title: t('metric.column.name'),
                    dataIndex: 'metric_key',
                    width: 100,
                    render: (key: string) => {
                      const meta = METRIC_GROUPS.find((g) => g.key === key);
                      return meta ? t(`metric.${meta.labelKey}`) : key;
                    }
                  },
                  {
                    title: t('metric.column.instance'),
                    dataIndex: 'index_key',
                    width: 160,
                    render: (v: string) => v || '—',
                    ellipsis: true
                  },
                  {
                    title: t('metric.column.severity'),
                    dataIndex: 'severity',
                    width: 70,
                    render: (sev: string | null) => (
                      <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>
                        {SEVERITY_LABEL_KEY[sev ?? ''] ? t(SEVERITY_LABEL_KEY[sev ?? '']) : sev ?? '—'}
                      </Tag>
                    )
                  },
                  {
                    title: t('metric.column.value'),
                    dataIndex: 'last_value',
                    render: (v: string | null) => v ?? '—'
                  },
                  {
                    title: t('metric.column.updatedAt'),
                    dataIndex: 'updated_at',
                    width: 160,
                    render: (v: string | null) => (v ? formatDateTime(v) : '—')
                  }
                ]}
                scroll={{ x: 'max-content' }}
              />
            </Card>
          </div>
        )}
      </div>
    </Card>
  );
}
