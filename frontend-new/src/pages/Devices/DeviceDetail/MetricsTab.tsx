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
  type DeviceMetricDashboardItem
} from '@/services/monitor';
import { ErrorBoundary } from '@/components/ErrorBoundary/ErrorBoundary';
import TrafficChart from '@/components/Monitor/TrafficChart';
import { formatDateTime } from '@/utils/format';

interface MetricGroupDef {
  key: string;
  label: string;
  icon: React.ReactNode;
  protocols?: string[];
}

const METRIC_GROUPS: MetricGroupDef[] = [
  {
    key: 'temperature',
    label: '温度',
    icon: <FireOutlined />,
    protocols: ['snmp', 'ipmi', 'zabbix']
  },
  { key: 'port_updown', label: '端口状态', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_status', label: '端口状态', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_in_errors', label: '入错包', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_out_errors', label: '出错包', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_in_discards', label: '入丢包', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_out_discards', label: '出丢包', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'if_utilization', label: '端口利用率', icon: <SwapOutlined />, protocols: ['snmp'] },
  { key: 'cpu_usage', label: 'CPU 利用率', icon: <ApiOutlined />, protocols: ['snmp', 'zabbix'] },
  {
    key: 'memory_usage',
    label: '内存利用率',
    icon: <DatabaseOutlined />,
    protocols: ['snmp', 'zabbix']
  },
  {
    key: 'sys_uptime',
    label: '系统运行时间',
    icon: <CheckCircleOutlined />,
    protocols: ['snmp', 'zabbix']
  },
  {
    key: 'fan_speed',
    label: '风扇转速',
    icon: <ApiOutlined />,
    protocols: ['snmp', 'ipmi', 'zabbix']
  },
  {
    key: 'zabbix_cpu_usage',
    label: 'CPU 利用率(Zabbix)',
    icon: <ApiOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_memory_usage',
    label: '内存利用率(Zabbix)',
    icon: <DatabaseOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_temperature',
    label: '温度(Zabbix)',
    icon: <FireOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_sys_uptime',
    label: '系统运行时间(Zabbix)',
    icon: <CheckCircleOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_in_errors',
    label: '入错包(Zabbix)',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_out_errors',
    label: '出错包(Zabbix)',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_in_discards',
    label: '入丢包(Zabbix)',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  {
    key: 'zabbix_if_out_discards',
    label: '出丢包(Zabbix)',
    icon: <SwapOutlined />,
    protocols: ['zabbix']
  },
  { key: 'raid_failure', label: 'RAID', icon: <DatabaseOutlined />, protocols: ['ipmi'] },
  { key: 'disk_failure', label: '磁盘', icon: <HddOutlined />, protocols: ['ipmi'] },
  { key: 'monitor_interrupted', label: '监控中断', icon: <DisconnectOutlined /> }
];

const SEVERITY_COLOR: Record<string, string> = {
  crit: 'red',
  critical: 'red',
  warn: 'orange',
  warning: 'orange',
  info: 'blue',
  ok: 'green'
};

const SEVERITY_LABEL: Record<string, string> = {
  crit: '严重',
  critical: '严重',
  warn: '警告',
  warning: '警告',
  info: '信息',
  ok: '正常'
};

const OVERALL_STATUS_META: Record<
  string,
  { text: string; type: 'error' | 'warning' | 'info' | 'success'; icon: React.ReactNode }
> = {
  no_credential: { text: '本机尚未关联监控凭据', type: 'warning', icon: <LockOutlined /> },
  not_probed: { text: '已配置凭据，等待首次探测', type: 'info', icon: <ClockCircleOutlined /> },
  unreachable: {
    text: '设备当前不可达，暂无指标数据',
    type: 'error',
    icon: <CloseCircleOutlined />
  },
  credential_error: {
    text: '监控凭据或配置异常，指标无法采集',
    type: 'warning',
    icon: <WarningOutlined />
  },
  no_data: { text: '尚未采集到指标数据', type: 'info', icon: <ClockCircleOutlined /> },
  breached: { text: '存在超阈值指标，请关注', type: 'warning', icon: <WarningOutlined /> },
  normal: { text: '指标采集正常', type: 'success', icon: <CheckCircleOutlined /> }
};

const STATUS_ONLY_OVERALL = new Set(['unreachable', 'credential_error', 'no_data', 'not_probed']);

interface MetricsTabProps {
  deviceId: number;
}

export default function MetricsTab({ deviceId }: MetricsTabProps) {
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
      <Card size="small" title="监控数据">
        <Empty
          image={<LockOutlined style={{ fontSize: 40, color: '#bbb' }} />}
          description={
            <Space direction="vertical" size={4} style={{ alignItems: 'center' }}>
              <Typography.Text strong>需要关联凭据</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                请到「监控凭据」Tab 关联至少一种监控凭据（SNMP / IPMI / Zabbix）后查看监控数据
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
  const statusReason = dashboard?.status_reason ?? overallMeta.text;

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

  return (
    <Card size="small" title="监控数据">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* ── 上半部分：Zabbix 端口流量（仅关联 Zabbix 凭据时显示） ── */}
        {showTraffic && (
          <ErrorBoundary
            fallback={() => (
              <Card size="small" title="端口流量">
                <div>流量图加载失败，请刷新重试</div>
              </Card>
            )}
          >
            <TrafficChart deviceId={deviceId} />
          </ErrorBoundary>
        )}

        {/* ── 下半部分：监控指标信息 ── */}
        <div>
          <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
            <Typography.Text strong>监控指标</Typography.Text>
            {dashboard?.template_group && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                指标模板组：{dashboard.template_group.name}
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
                      错误详情：{dashboard.last_error}
                    </Typography.Text>
                  )}
                  {overall === 'credential_error' && dashboard?.last_error && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      错误详情：{dashboard.last_error}
                    </Typography.Text>
                  )}
                  {dashboard?.last_checked_at && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      最近探测：{formatDateTime(dashboard.last_checked_at)}
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
                <Table<DeviceMetricDashboardItem>
                  dataSource={metricStatus}
                  rowKey="metric_key"
                  size="small"
                  pagination={false}
                  columns={[
                    {
                      title: '指标',
                      dataIndex: 'metric_name',
                      render: (v: string, r) => r.metric_name || r.metric_key
                    },
                    {
                      title: '来源',
                      dataIndex: 'source',
                      width: 90,
                      render: (v: string | null) => (v ? v.toUpperCase() : '—')
                    },
                    {
                      title: '当前值',
                      dataIndex: 'value',
                      width: 110,
                      render: (v: string | null) => v ?? '—'
                    },
                    {
                      title: '状态',
                      key: 'status',
                      width: 100,
                      render: (_: unknown, r: DeviceMetricDashboardItem) =>
                        r.breached ? (
                          <Tag color={SEVERITY_COLOR[r.severity ?? ''] ?? 'orange'}>
                            {SEVERITY_LABEL[r.severity ?? ''] ?? '告警'}
                          </Tag>
                        ) : r.value != null ? (
                          <Tag color="green">正常</Tag>
                        ) : (
                          <Tag color="default">无数据</Tag>
                        )
                    },
                    {
                      title: '采集时间',
                      dataIndex: 'collected_at',
                      width: 160,
                      render: (v: string | null) => (v ? formatDateTime(v) : '—')
                    }
                  ]}
                />
              </Card>
            ) : (
              <Empty description="该模板组暂未包含任何指标" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )
          ) : /* 未命中模板组 → 优先用 latest 数值表格；无 latest 时回退默认分组 + 告警卡片 */
          metricStatus.length > 0 ? (
            <Card
              size="small"
              style={{ background: '#fafafa', borderColor: '#d9d9d9' }}
              styles={{ body: { padding: 0 } }}
            >
              <Table<DeviceMetricDashboardItem>
                dataSource={metricStatus}
                rowKey="metric_key"
                size="small"
                pagination={false}
                columns={[
                  {
                    title: '指标',
                    dataIndex: 'metric_name',
                    render: (v: string, r) => r.metric_name || r.metric_key
                  },
                  {
                    title: '来源',
                    dataIndex: 'source',
                    width: 90,
                    render: (v: string | null) => (v ? v.toUpperCase() : '—')
                  },
                  {
                    title: '当前值',
                    dataIndex: 'value',
                    width: 110,
                    render: (v: string | null) => v ?? '—'
                  },
                  {
                    title: '状态',
                    key: 'status',
                    width: 100,
                    render: (_: unknown, r: DeviceMetricDashboardItem) =>
                      r.breached ? (
                        <Tag color={SEVERITY_COLOR[r.severity ?? ''] ?? 'orange'}>
                          {SEVERITY_LABEL[r.severity ?? ''] ?? '告警'}
                        </Tag>
                      ) : r.value != null ? (
                        <Tag color="green">正常</Tag>
                      ) : (
                        <Tag color="default">无数据</Tag>
                      )
                  },
                  {
                    title: '采集时间',
                    dataIndex: 'collected_at',
                    width: 160,
                    render: (v: string | null) => (v ? formatDateTime(v) : '—')
                  }
                ]}
              />
            </Card>
          ) : (
            <>
              {items.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message={`${items.length} 条活跃指标告警`}
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
                            <span style={{ marginLeft: 8 }}>{group.label}</span>
                            {hasAlert && (
                              <Tag
                                color={SEVERITY_COLOR[groupItems[0]?.severity ?? ''] ?? 'orange'}
                                style={{ marginLeft: 8 }}
                              >
                                {groupItems.length} 告警
                              </Tag>
                            )}
                          </span>
                        }
                        style={{ background: '#fafafa', borderColor: '#d9d9d9' }}
                      >
                        {group.key === 'monitor_interrupted' ? (
                          hasAlert ? (
                            <Tag color="orange">监控中断</Tag>
                          ) : notProbedYet ? (
                            <Tag color="default">等待探测</Tag>
                          ) : (
                            <Tag color="green">正常</Tag>
                          )
                        ) : groupItems.length > 0 ? (
                          <Table
                            dataSource={groupItems}
                            rowKey="id"
                            size="small"
                            pagination={false}
                            columns={[
                              {
                                title: '实例',
                                dataIndex: 'index_key',
                                render: (v: string) => v || '—',
                                ellipsis: true
                              },
                              {
                                title: '级别',
                                dataIndex: 'severity',
                                width: 70,
                                render: (sev: string | null) => (
                                  <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>
                                    {SEVERITY_LABEL[sev ?? ''] ?? sev ?? '—'}
                                  </Tag>
                                )
                              },
                              {
                                title: '当前值',
                                dataIndex: 'last_value',
                                width: 80,
                                render: (v: string | null) => v ?? '—'
                              }
                            ]}
                          />
                        ) : notProbedYet ? (
                          <Tag color="default">等待探测</Tag>
                        ) : (
                          <Tag color="green">正常</Tag>
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
              <Typography.Text strong>活跃告警明细</Typography.Text>
              <Tag color="orange">{items.length} 条</Tag>
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
                    title: '指标',
                    dataIndex: 'metric_key',
                    width: 100,
                    render: (key: string) => {
                      const meta = METRIC_GROUPS.find((g) => g.key === key);
                      return meta?.label ?? key;
                    }
                  },
                  {
                    title: '实例',
                    dataIndex: 'index_key',
                    width: 160,
                    render: (v: string) => v || '—',
                    ellipsis: true
                  },
                  {
                    title: '级别',
                    dataIndex: 'severity',
                    width: 70,
                    render: (sev: string | null) => (
                      <Tag color={SEVERITY_COLOR[sev ?? ''] ?? 'default'}>
                        {SEVERITY_LABEL[sev ?? ''] ?? sev ?? '—'}
                      </Tag>
                    )
                  },
                  {
                    title: '当前值',
                    dataIndex: 'last_value',
                    render: (v: string | null) => v ?? '—'
                  },
                  {
                    title: '更新时间',
                    dataIndex: 'updated_at',
                    width: 160,
                    render: (v: string | null) => (v ? formatDateTime(v) : '—')
                  }
                ]}
              />
            </Card>
          </div>
        )}
      </div>
    </Card>
  );
}
