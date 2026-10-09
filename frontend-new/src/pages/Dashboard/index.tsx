import React, { useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Spin,
  Timeline,
  Badge,
  theme,
  Progress,
  Space,
  Tooltip,
  Button
} from 'antd';
import {
  HomeOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  TeamOutlined,
  LockOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  DashboardOutlined,
  SwapOutlined,
  ClockCircleOutlined,
  ClusterOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { Pie } from '@ant-design/charts';
import {
  useDashboardSuspenseStats,
  useDashboardActivities,
  useSystemStatus
} from '@/services/dashboard';
import { useMonitorOverview, useIncidents } from '@/services/monitor';
import { CabinetStatusCode } from '@/types/enums';
import type { ComponentHealth } from '@/types/models';
import { getCabinetStatusMeta, getDeviceStatusEntries } from '@/types/statusMeta';
import { calcHealthScore } from '@/utils/monitorHealth';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';
import { useResponsive } from '@/hooks/useResponsive';

const { useToken } = theme;


interface RingChartProps {
  data: { type: string; value: number; color: string }[];
  title: string;
  height?: number;
}

function RingChart({ data, title, height = 240 }: RingChartProps) {
  const { token } = useToken();
  const { t } = useTranslation('monitor');
  const { t: tCommon } = useTranslation('common');
  const validData = useMemo(() => data.filter((d) => d.value > 0), [data]);
  const total = useMemo(() => data.reduce((s, d) => s + d.value, 0), [data]);

  const config = useMemo(
    () => ({
      appendPadding: [8, 8, 8, 8] as [number, number, number, number],
      data:
        validData.length > 0
          ? validData
          : [{ type: tCommon('message.noData'), value: 1, color: token.colorBgContainer }],
      angleField: 'value',
      colorField: 'type',
      color: validData.length > 0 ? validData.map((d) => d.color) : [token.colorBgContainer],
      tooltip: {
        title: 'type',
        items: [{ field: 'value', name: t('chart.count') }]
      },
      radius: 0.88,
      innerRadius: 0.68,
      label: false as const,
      statistic: {
        title: {
          content: title,
          style: {
            fontSize: '12px',
            color: token.colorTextSecondary,
            lineHeight: '16px'
          }
        },
        content: {
          style: {
            fontSize: '24px',
            fontWeight: 700,
            color: token.colorText,
            lineHeight: '30px'
          },
          formatter: () => total.toLocaleString()
        }
      },
      legend: {
        position: 'bottom' as const,
        layout: 'horizontal',
        itemSpacing: 8,
        label: {
          style: { fontSize: 11, fill: token.colorTextSecondary }
        }
      },
      interactions: [{ type: 'element-active' }],
      animation: { appear: { duration: 600, easing: 'easeQuadOut' } },
      pieStyle: { lineWidth: 2, stroke: token.colorBgElevated }
    }),
    [validData, title, total, token, t, tCommon]
  );

  return <Pie {...config} height={height} />;
}


interface MetricCardProps {
  title: string;
  value: number;
  suffix?: string;
  icon: React.ReactNode;
  color: string;
  subtitle?: string;
}

function MetricCard({ title, value, suffix, icon, color, subtitle }: MetricCardProps) {
  const { token } = useToken();

  return (
    <Card
      size="small"
      style={{
        cursor: 'default',
        borderLeft: `3px solid ${color}`,
        borderRadius: token.borderRadiusLG,
        overflow: 'hidden'
      }}
      styles={{
        body: {
          padding: '14px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12
        }
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: token.borderRadius,
          background: `${color}15`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}
      >
        <span style={{ color, fontSize: 20 }}>{icon}</span>
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 2 }}>
          {title}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: token.colorText, lineHeight: 1.2 }}>
            {typeof value === 'number' ? value.toLocaleString() : value}
          </span>
          {suffix && (
            <span style={{ fontSize: 13, color: token.colorTextSecondary }}>{suffix}</span>
          )}
        </div>
        {subtitle && (
          <div style={{ fontSize: 11, color: token.colorTextDisabled, marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
    </Card>
  );
}


function SystemStatusCard() {
  const { data: status } = useSystemStatus();
  const { token } = useToken();
  const { t } = useTranslation('monitor');
  const { t: tDevice } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');

  const overallConfig: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
    healthy: {
      color: token.colorSuccess,
      icon: <CheckCircleOutlined />,
      text: t('dashboard.status.normal')
    },
    warning: {
      color: token.colorWarning,
      icon: <WarningOutlined />,
      text: t('dashboard.status.warning')
    },
    critical: {
      color: token.colorError,
      icon: <CloseCircleOutlined />,
      text: t('dashboard.status.critical')
    },
    unknown: {
      color: token.colorTextDisabled,
      icon: <QuestionCircleOutlined />,
      text: tCommon('field.unknown')
    }
  };

  const current = overallConfig[status?.overall || 'unknown'] || overallConfig.unknown;
  const perf = status?.performance;

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined />
          <span>{t('dashboard.systemStatus')}</span>
        </Space>
      }
      size="small"
      extra={
        <Badge
          color={current.color}
          text={
            <span style={{ color: current.color, fontWeight: 600, fontSize: 13 }}>
              {current.text}
            </span>
          }
        />
      }
      style={{ height: '100%' }}
    >
      {perf ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[
            { label: 'CPU', value: perf.cpu, detail: `${perf.cpu.toFixed(1)}%` },
            {
              label: tDevice('field.memory'),
              value: perf.memory,
              detail: `${perf.memory_used?.toFixed(1) ?? '--'}G / ${perf.memory_total?.toFixed(1) ?? '--'}G`
            },
            {
              label: t('dashboard.perf.disk'),
              value: perf.disk,
              detail: `${perf.disk_used?.toFixed(1) ?? '--'}G / ${perf.disk_total?.toFixed(1) ?? '--'}G`
            }
          ].map((item) => (
            <div key={item.label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: token.colorTextSecondary, fontWeight: 500 }}>
                  {item.label}
                </span>
                <span style={{ fontSize: 12, color: token.colorText }}>{item.detail}</span>
              </div>
              <Progress
                percent={Math.min(item.value, 100)}
                showInfo={false}
                strokeColor={
                  item.value > 80
                    ? token.colorError
                    : item.value > 60
                      ? token.colorWarning
                      : token.colorSuccess
                }
                railColor={token.colorBgContainer}
                size="small"
                style={{ margin: 0 }}
              />
            </div>
          ))}
          <div
            style={{
              fontSize: 11,
              color: token.colorTextDisabled,
              marginTop: 2,
              textAlign: 'right'
            }}
          >
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            {status?.lastUpdated ? formatDateTime(status.lastUpdated) : '--'}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '24px 0', color: token.colorTextDisabled }}>
          {tCommon('message.noData')}
        </div>
      )}
    </Card>
  );
}


function ActivityTimeline() {
  const { data: activityData, isLoading } = useDashboardActivities(3);
  const { token } = useToken();
  const { t } = useTranslation('monitor');

  const colorMap: Record<string, string> = {
    blue: token.colorPrimary,
    green: token.colorSuccess,
    orange: token.colorWarning,
    purple: token.purple6,
    cyan: token.cyan6,
    default: token.colorTextSecondary
  };

  const activities = activityData?.activities || [];

  return (
    <Card
      title={
        <Space>
          <ClockCircleOutlined />
          <span>{t('dashboard.recentActivity')}</span>
        </Space>
      }
      size="small"
      style={{ height: '100%' }}
    >
      <Spin spinning={isLoading}>
        {activities.length > 0 ? (
          <Timeline
            items={activities.slice(0, 3).map((act) => ({
              color: colorMap[act.color] || token.colorPrimary,
              content: (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: token.colorText }}>
                    {act.title}
                  </div>
                  <div style={{ fontSize: 12, color: token.colorTextSecondary, marginTop: 2 }}>
                    {act.description}
                  </div>
                  <div style={{ fontSize: 11, color: token.colorTextDisabled, marginTop: 2 }}>
                    {act.user} · {act.timestamp ? formatDateTime(act.timestamp) : '--'}
                  </div>
                </div>
              )
            }))}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: '24px 0', color: token.colorTextDisabled }}>
            {t('dashboard.noActivity')}
          </div>
        )}
      </Spin>
    </Card>
  );
}


function UtilizationGauges() {
  const { data: stats } = useDashboardSuspenseStats();
  const { token } = useToken();
  const { t } = useTranslation('monitor');

  const gauges = [
    {
      label: t('dashboard.utilization.cabinet'),
      value: stats?.percentages?.cabinet_utilization ?? 0,
      color: token.colorPrimary,
      detail: `${stats?.cabinets?.occupied ?? 0} / ${stats?.cabinets?.total ?? 0}`
    },
    {
      label: t('dashboard.utilization.ip'),
      value: stats?.percentages?.ip_utilization ?? 0,
      color: token.colorSuccess,
      detail: `${stats?.networks?.ips_used ?? 0} / ${stats?.networks?.ips_total ?? 0}`
    },
    {
      label: t('dashboard.utilization.deviceOnline'),
      value: stats?.percentages?.device_online_rate ?? 0,
      color: token.colorWarning,
      detail: `${stats?.devices?.online ?? 0} / ${stats?.devices?.total ?? 0}`
    }
  ];

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined />
          <span>{t('dashboard.utilization.title')}</span>
        </Space>
      }
      size="small"
      style={{ height: '100%' }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '4px 0' }}>
        {gauges.map((item) => (
          <div key={item.label}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 13, color: token.colorText, fontWeight: 500 }}>
                {item.label}
              </span>
              <Space size={4}>
                <span style={{ fontSize: 12, color: token.colorTextSecondary }}>{item.detail}</span>
                <span style={{ fontSize: 16, fontWeight: 700, color: item.color }}>
                  {item.value.toFixed(1)}%
                </span>
              </Space>
            </div>
            <Progress
              percent={Math.min(item.value, 100)}
              showInfo={false}
              strokeColor={item.color}
              railColor={token.colorBgContainer}
              size="small"
              style={{ margin: 0 }}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}


function MonitorOverviewCard() {
  const { token } = useToken();
  const { t } = useTranslation('monitor');
  const { t: tCommon } = useTranslation('common');
  const {
    data: overview,
    isError: overviewErr,
    isFetching,
    refetch,
    dataUpdatedAt
  } = useMonitorOverview();
  const { data: incidents, isError: incidentsErr, refetch: refetchIncidents } = useIncidents();

  const healthScore = overview ? calcHealthScore(overview) : null;
  const scoreColor =
    healthScore == null
      ? undefined
      : healthScore >= 90
        ? token.colorSuccess
        : healthScore >= 70
          ? token.colorWarning
          : token.colorError;
  const monitorUnavailable = overviewErr || incidentsErr;
  const openIncidents = incidents?.total ?? 0;
  const pausedDevices = overview?.paused_devices ?? 0;
  const monitorItems = overview
    ? [
        {
          label: t('dashboard.monitorOverview.reachable'),
          value: overview.reachable ?? 0,
          color: token.colorSuccess
        },
        {
          label: t('dashboard.monitorOverview.unreachable'),
          value: overview.unreachable ?? 0,
          color: token.colorError
        },
        {
          label: t('dashboard.monitorOverview.flapping'),
          value: overview.flapping ?? 0,
          color: token.colorWarning
        },
        {
          label: t('dashboard.monitorOverview.blindspot'),
          value: overview.alert_blindspot ?? 0,
          color: token.colorErrorActive
        }
      ]
    : [];

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined />
          <span>{t('dashboard.monitorOverview.title')}</span>
        </Space>
      }
      size="small"
      style={{ height: '100%' }}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 10 } }}
      extra={
        <Tooltip title={tCommon('action.refresh')}>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            loading={isFetching}
            aria-label={tCommon('action.refresh')}
            onClick={() => {
              refetch();
              refetchIncidents();
            }}
          />
        </Tooltip>
      }
    >
      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 8
          }}
        >
          <span style={{ fontSize: 12, color: token.colorTextSecondary, fontWeight: 600 }}>
            {t('dashboard.monitorOverview.monitoredObjects')}
          </span>
          {healthScore != null && (
            <span style={{ fontSize: 12, fontWeight: 700, color: scoreColor }}>
              {t('dashboard.monitorOverview.healthScore')} {healthScore}
            </span>
          )}
        </div>
        {monitorUnavailable ? (
          <div style={{ fontSize: 12, color: token.colorTextDisabled }}>
            {tCommon('message.noPermission')}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px' }}>
            {monitorItems.map((it) => (
              <div
                key={it.label}
                style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}
              >
                <span style={{ color: token.colorTextSecondary }}>{it.label}</span>
                <span style={{ fontWeight: 600, color: it.value > 0 ? it.color : token.colorText }}>
                  {it.value}
                </span>
              </div>
            ))}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: token.colorTextSecondary }}>
                {t('dashboard.monitorOverview.openIncidents')}
              </span>
              <span
                style={{
                  fontWeight: 600,
                  color: openIncidents > 0 ? token.colorWarning : token.colorText
                }}
              >
                {openIncidents}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 布局债纪律（B5 清理，2026-10-08）：此处原本用 justifyContent 的两端对齐值，
          窄屏下它会把两个 span 死死顶到左右两端，中间只剩 gap —— 提示文字一长，
          时间戳就被压到换行且两端参差。改 flexWrap：空间不足时时间戳整块落到下一行，
          不再互相挤压；宽屏下由 marginLeft:auto 保持时间戳右对齐，视觉与原状一致。
          注：本注释刻意不写该取值的字面量 —— layout-ratchet 按正则计数且不区分注释，
          写全称会把基线数字抬高，与 §17.12.4 的 important 口径同理。 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          fontSize: 11,
          color: token.colorTextDisabled
        }}
      >
        {/* 暂停探测的设备已被后端排除在上面的统计之外，此处显式说明，
            否则运维会疑惑"设备总数怎么少了" */}
        <span>
          {pausedDevices > 0 ? t('dashboard.monitorOverview.paused', { count: pausedDevices }) : ''}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {dataUpdatedAt ? formatDateTime(new Date(dataUpdatedAt).toISOString()) : '--'}
        </span>
      </div>
    </Card>
  );
}


function ComponentHealthCard() {
  const { token } = useToken();
  const { t } = useTranslation('monitor');
  const { t: tCommon } = useTranslation('common');
  const { data: status } = useSystemStatus();

  const services = status?.services ?? {};
  const serviceOrder = ['database', 'redis', 'api', 'gateway', 'monitor', 'celery'];
  const serviceList: [string, ComponentHealth][] = [
    ...serviceOrder
      .filter((k) => k in services)
      .map((k) => [k, services[k]] as [string, ComponentHealth]),
    ...(Object.entries(services) as [string, ComponentHealth][]).filter(
      ([k]) => !serviceOrder.includes(k)
    )
  ];
  const statusMeta: Record<string, { color: string }> = {
    running: { color: token.colorSuccess },
    degraded: { color: token.colorWarning },
    down: { color: token.colorError },
    unknown: { color: token.colorTextDisabled }
  };
  const serviceNames: Record<string, string> = {
    database: t('dashboard.componentHealth.service.database'),
    redis: t('dashboard.componentHealth.service.redis'),
    api: t('dashboard.componentHealth.service.api'),
    gateway: t('dashboard.componentHealth.service.gateway'),
    monitor: t('dashboard.componentHealth.service.monitor'),
    celery: t('dashboard.componentHealth.service.celery')
  };
  const serviceLabel = (k: string) => serviceNames[k] ?? k;
  const statusNames: Record<string, string> = {
    running: t('dashboard.componentHealth.status.running'),
    degraded: t('dashboard.componentHealth.status.degraded'),
    down: t('dashboard.componentHealth.status.down'),
    unknown: t('dashboard.componentHealth.status.unknown')
  };
  const statusLabel = (s: string) => statusNames[s] ?? s;
  const detailText = (c: ComponentHealth) => {
    if (c.latency_ms != null) return `${c.latency_ms.toFixed(1)} ms`;
    if (c.age_seconds != null)
      return `${t('dashboard.componentHealth.heartbeat')} ${c.age_seconds.toFixed(0)}s`;
    if (c.workers != null) return `${c.workers} workers`;
    return '';
  };

  return (
    <Card
      title={
        <Space>
          <ClusterOutlined />
          <span>{t('dashboard.componentHealth.title')}</span>
        </Space>
      }
      size="small"
      style={{ height: '100%' }}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 8 } }}
    >
      {/* 后端服务组件 */}
      <div>
        <div
          style={{
            fontSize: 12,
            color: token.colorTextSecondary,
            fontWeight: 600,
            marginBottom: 8
          }}
        >
          {t('dashboard.componentHealth.services')}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {serviceList.length > 0 ? (
            serviceList.map(([name, c]) => (
              <div
                key={name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: 12
                }}
              >
                <span
                  style={{ display: 'flex', alignItems: 'center', gap: 6, color: token.colorText }}
                >
                  <Badge color={statusMeta[c.status]?.color ?? token.colorTextDisabled} />
                  {serviceLabel(name)}
                </span>
                <span style={{ color: token.colorTextSecondary }}>
                  {statusLabel(c.status)}
                  {detailText(c) ? ` · ${detailText(c)}` : ''}
                </span>
              </div>
            ))
          ) : (
            <div style={{ fontSize: 12, color: token.colorTextDisabled }}>
              {tCommon('message.noData')}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}


function Dashboard() {
  const { t } = useTranslation('monitor');
  const { t: tDevice } = useTranslation('device');
  const { isMobile } = useResponsive();
  const { token } = useToken();
  const { data: stats } = useDashboardSuspenseStats();

  const publicGroup = useMemo(
    () =>
      stats?.networks?.public_ips ?? { total: 0, active: 0, inactive: 0, blocked: 0, unused: 0 },
    [stats]
  );
  const privateGroup = useMemo(
    () =>
      stats?.networks?.private_ips ?? { total: 0, active: 0, inactive: 0, blocked: 0, unused: 0 },
    [stats]
  );

  const deviceChartData = useMemo(() => {
    const dist = stats?.devices?.status_distribution ?? {};
    return getDeviceStatusEntries(tDevice).map(({ code, label, color }) => ({
      type: label,
      value: dist[code] ?? 0,
      color
    }));
  }, [stats?.devices?.status_distribution, tDevice]);

  const cabinetChartData = useMemo(() => {
    const c = stats?.cabinets;
    const m = (code: CabinetStatusCode) => getCabinetStatusMeta(code, tDevice);
    return [
      {
        type: m(CabinetStatusCode.AVAILABLE)?.label ?? '',
        value: c?.available ?? 0,
        color: m(CabinetStatusCode.AVAILABLE)?.color ?? 'default'
      },
      {
        type: m(CabinetStatusCode.IN_USE)?.label ?? '',
        value: c?.occupied ?? 0,
        color: m(CabinetStatusCode.IN_USE)?.color ?? 'default'
      },
      {
        type: m(CabinetStatusCode.MAINTENANCE)?.label ?? '',
        value: c?.maintenance ?? 0,
        color: m(CabinetStatusCode.MAINTENANCE)?.color ?? 'default'
      },
      {
        type: m(CabinetStatusCode.RESERVED)?.label ?? '',
        value: c?.reserved ?? 0,
        color: m(CabinetStatusCode.RESERVED)?.color ?? 'default'
      },
      {
        type: m(CabinetStatusCode.DISABLED)?.label ?? '',
        value: c?.disabled ?? 0,
        color: m(CabinetStatusCode.DISABLED)?.color ?? 'default'
      }
    ];
  }, [stats?.cabinets, tDevice]);

  const ipChartData = useMemo(() => {
    return [
      {
        type: t('dashboard.ip.publicActive'),
        value: publicGroup.active,
        color: token.colorPrimary
      },
      {
        type: t('dashboard.ip.publicInactive'),
        value: publicGroup.inactive,
        color: token.blue4
      },
      {
        type: t('dashboard.ip.publicBlocked'),
        value: publicGroup.blocked,
        color: token.colorError
      },
      {
        type: t('dashboard.ip.publicUnused'),
        value: publicGroup.unused,
        color: token.blue2
      },
      {
        type: t('dashboard.ip.privateActive'),
        value: privateGroup.active,
        color: token.colorSuccess
      },
      {
        type: t('dashboard.ip.privateInactive'),
        value: privateGroup.inactive,
        color: token.green4
      },
      {
        type: t('dashboard.ip.privateBlocked'),
        value: privateGroup.blocked,
        color: token.red4
      },
      {
        type: t('dashboard.ip.privateUnused'),
        value: privateGroup.unused,
        color: token.green2
      }
    ].filter((d) => d.value > 0);
  }, [publicGroup, privateGroup, t, token]);

  const metricCards = [
    {
      title: t('dashboard.metric.roomTotal'),
      value: stats?.rooms?.total ?? 0,
      icon: <HomeOutlined />,
      color: token.colorPrimary,
      subtitle: t('dashboard.subtitle.active', { count: stats?.rooms?.active ?? 0 })
    },
    {
      title: t('dashboard.metric.cabinetTotal'),
      value: stats?.cabinets?.total ?? 0,
      icon: <DatabaseOutlined />,
      color: token.purple6,
      subtitle: t('dashboard.subtitle.available', { count: stats?.cabinets?.available ?? 0 })
    },
    {
      title: t('chart.deviceTotal'),
      value: stats?.devices?.total ?? 0,
      icon: <CloudServerOutlined />,
      color: token.cyan6,
      subtitle: t('dashboard.subtitle.online', { count: stats?.devices?.online ?? 0 })
    },
    {
      title: t('dashboard.metric.customerTotal'),
      value: stats?.customers?.total ?? 0,
      icon: <TeamOutlined />,
      color: token.orange6,
      subtitle: t('dashboard.subtitle.active', { count: stats?.customers?.active ?? 0 })
    },
    {
      title: t('dashboard.metric.publicIp'),
      value: publicGroup.total,
      icon: <GlobalOutlined />,
      color: token.colorPrimary,
      subtitle: t('dashboard.subtitle.active', { count: publicGroup.active })
    },
    {
      title: t('dashboard.metric.privateIp'),
      value: privateGroup.total,
      icon: <LockOutlined />,
      color: token.colorSuccess,
      subtitle: t('dashboard.subtitle.active', { count: privateGroup.active })
    },
    {
      title: tDevice('deviceSubtype.SWITCH'),
      value: stats?.switches?.total ?? 0,
      icon: <SwapOutlined />,
      color: token.magenta6,
      subtitle: t('dashboard.subtitle.segments', { count: stats?.networks?.segments ?? 0 })
    },
    {
      title: t('dashboard.utilization.deviceOnline'),
      value: stats?.percentages?.device_online_rate ?? 0,
      suffix: '%',
      icon: <CheckCircleOutlined />,
      color:
        (stats?.percentages?.device_online_rate ?? 0) > 80
          ? token.colorSuccess
          : token.colorWarning,
      subtitle: t('dashboard.subtitle.onlineRatio', {
        online: stats?.devices?.online ?? 0,
        total: stats?.devices?.total ?? 0
      })
    }
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* 第一行：核心指标卡片 */}
      <Row gutter={[12, 12]}>
        {metricCards.map((card) => (
          <Col xs={12} sm={8} md={6} lg={3} key={card.title}>
            <MetricCard
              title={card.title}
              value={card.value}
              suffix={card.suffix}
              icon={card.icon}
              color={card.color}
              subtitle={card.subtitle}
            />
          </Col>
        ))}
      </Row>

      {/* 第二行：三列环形图 — 设备/机柜/IP 状态分布 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={8}>
          <Card size="small" title={t('dashboard.chart.deviceStatus')} style={{ height: '100%' }}>
            <RingChart
              data={deviceChartData}
              title={t('column.device')}
              height={isMobile ? 220 : 280}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title={t('dashboard.chart.cabinetStatus')} style={{ height: '100%' }}>
            <RingChart
              data={cabinetChartData}
              title={tDevice('field.cabinet')}
              height={isMobile ? 220 : 280}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title={t('dashboard.chart.ipStatus')} style={{ height: '100%' }}>
            <RingChart data={ipChartData} title="IP" height={isMobile ? 220 : 280} />
          </Card>
        </Col>
      </Row>

      {/* 第三行：资源利用率 + 系统状态 + 监控概览 + 组件健康
          （「监控概览」2026-10-08 从「组件健康」拆出：原卡两段内容高度不等，
            同排被拉齐后留白；拆成两张等高的卡后与邻居对齐） */}
      <Row gutter={[12, 12]} align="stretch" style={{ marginTop: 12 }}>
        <Col xs={24} sm={12} lg={6}>
          <UtilizationGauges />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <SystemStatusCard />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <MonitorOverviewCard />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <ComponentHealthCard />
        </Col>
      </Row>

      {/* 第四行：最近活动流（列表型内容，独占一行） */}
      <Row gutter={[12, 12]} align="stretch" style={{ marginTop: 12 }}>
        <Col xs={24}>
          <ActivityTimeline />
        </Col>
      </Row>
    </div>
  );
}

export default Dashboard;
