/**
 * 仪表盘页面 — 运营监控中心
 *
 * 设计系统 (UI-UX-Pro-Max):
 * - 风格: Dark Mode (OLED) — 深色监控中心
 * - 配色: Primary #0F172A / CTA #22C55E / BG #020617 / Text #F8FAFC
 * - 字体: 系统默认 (Ant Design 体系)
 * - 图表: 环形图 + 仪表盘进度条 + 实时刷新
 * - 布局: 大屏友好三栏布局，信息密度高
 *
 * 布局结构：
 * 1. 顶部核心指标卡片（机房/机柜/设备/客户/IP/交换机/在线率/利用率）
 * 2. 中部可视化区域（设备状态环形图 + 机柜状态环形图 + IP状态环形图）
 * 3. 底部信息区域（资源利用率仪表盘 + 系统状态 + 最近活动流）
 */
import React, { useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Statistic,
  Spin,
  Tag,
  Timeline,
  Badge,
  theme,
  Tooltip,
  Progress,
  Flex,
  Space,
  Divider
} from 'antd';
import {
  HomeOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  TeamOutlined,
  LockOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  DashboardOutlined,
  SwapOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import { Pie } from '@ant-design/charts';
import {
  useDashboardSuspenseStats,
  useDashboardActivities,
  useSystemStatus
} from '@/services/dashboard';
import { CabinetStatusCode } from '@/types/enums';
import { getCabinetStatusMeta, getDeviceStatusEntries } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { DeviceStatusCode, IPStatusCode } from '@/types/enums';
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
    purple: '#722ed1',
    cyan: '#13c2c2',
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


function Dashboard() {
  const { t } = useTranslation('monitor');
  const { t: tDevice } = useTranslation('device');
  const { isMobile } = useResponsive();
  const { data: stats } = useDashboardSuspenseStats();
  const { token } = useToken();

  const publicGroup = stats?.networks?.public_ips ?? {
    total: 0,
    active: 0,
    inactive: 0,
    blocked: 0,
    unused: 0
  };
  const privateGroup = stats?.networks?.private_ips ?? {
    total: 0,
    active: 0,
    inactive: 0,
    blocked: 0,
    unused: 0
  };

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
      { type: t('dashboard.ip.publicActive'), value: publicGroup.active, color: '#1890ff' },
      { type: t('dashboard.ip.publicInactive'), value: publicGroup.inactive, color: '#69c0ff' },
      { type: t('dashboard.ip.publicBlocked'), value: publicGroup.blocked, color: '#ff4d4f' },
      { type: t('dashboard.ip.publicUnused'), value: publicGroup.unused, color: '#bae7ff' },
      { type: t('dashboard.ip.privateActive'), value: privateGroup.active, color: '#52c41a' },
      { type: t('dashboard.ip.privateInactive'), value: privateGroup.inactive, color: '#95de64' },
      { type: t('dashboard.ip.privateBlocked'), value: privateGroup.blocked, color: '#ff7875' },
      { type: t('dashboard.ip.privateUnused'), value: privateGroup.unused, color: '#d9f7be' }
    ].filter((d) => d.value > 0);
  }, [publicGroup, privateGroup, t]);

  const metricCards = [
    {
      title: t('dashboard.metric.roomTotal'),
      value: stats?.rooms?.total ?? 0,
      icon: <HomeOutlined />,
      color: '#1890ff',
      subtitle: t('dashboard.subtitle.active', { count: stats?.rooms?.active ?? 0 })
    },
    {
      title: t('dashboard.metric.cabinetTotal'),
      value: stats?.cabinets?.total ?? 0,
      icon: <DatabaseOutlined />,
      color: '#722ed1',
      subtitle: t('dashboard.subtitle.available', { count: stats?.cabinets?.available ?? 0 })
    },
    {
      title: t('chart.deviceTotal'),
      value: stats?.devices?.total ?? 0,
      icon: <CloudServerOutlined />,
      color: '#13c2c2',
      subtitle: t('dashboard.subtitle.online', { count: stats?.devices?.online ?? 0 })
    },
    {
      title: t('dashboard.metric.customerTotal'),
      value: stats?.customers?.total ?? 0,
      icon: <TeamOutlined />,
      color: '#fa8c16',
      subtitle: t('dashboard.subtitle.active', { count: stats?.customers?.active ?? 0 })
    },
    {
      title: t('dashboard.metric.publicIp'),
      value: publicGroup.total,
      icon: <GlobalOutlined />,
      color: '#1890ff',
      subtitle: t('dashboard.subtitle.active', { count: publicGroup.active })
    },
    {
      title: t('dashboard.metric.privateIp'),
      value: privateGroup.total,
      icon: <LockOutlined />,
      color: '#52c41a',
      subtitle: t('dashboard.subtitle.active', { count: privateGroup.active })
    },
    {
      title: tDevice('deviceSubtype.SWITCH'),
      value: stats?.switches?.total ?? 0,
      icon: <SwapOutlined />,
      color: '#eb2f96',
      subtitle: t('dashboard.subtitle.segments', { count: stats?.networks?.segments ?? 0 })
    },
    {
      title: t('dashboard.utilization.deviceOnline'),
      value: stats?.percentages?.device_online_rate ?? 0,
      suffix: '%',
      icon: <CheckCircleOutlined />,
      color: (stats?.percentages?.device_online_rate ?? 0) > 80 ? '#52c41a' : '#faad14',
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

      {/* 第三行：资源利用率 + 系统状态 + 活动流 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={8}>
          <UtilizationGauges />
        </Col>
        <Col xs={24} lg={8}>
          <SystemStatusCard />
        </Col>
        <Col xs={24} lg={8}>
          <ActivityTimeline />
        </Col>
      </Row>
    </div>
  );
}

export default Dashboard;
