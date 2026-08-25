/**
 * 监控总览 - 顶部 KPI 概览区 + 健康度仪表盘
 *
 * 重构（M29）：从 10 个平铺卡片精简为 4 核心 KPI + 健康度评分，
 * 突出关键信息层次，符合 Real-Time Monitoring 设计风格。
 *
 * 布局：
 * - 左侧：4 核心 KPI 卡片（监控设备/可用率/活跃告警/盲区）大字号突出
 * - 右侧：健康度仪表盘（综合可用率+告警权重，0-100 分）
 *
 * 健康度算法：可用率 * 0.6 + (1 - 告警设备占比) * 0.3 + (1 - 中断占比) * 0.1
 */
import { Card, Col, Row, Statistic, Typography, theme, Progress } from 'antd';
import {
  CheckCircleOutlined,
  WarningOutlined,
  EyeInvisibleOutlined,
  MonitorOutlined,
  SettingOutlined
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { Button, Space } from 'antd';
import type { MonitorOverviewData } from '@/services/monitor';

const { Text } = Typography;

interface StatCardsProps {
  overview: MonitorOverviewData | undefined;
  loading: boolean;
}


function calcHealthScore(overview: MonitorOverviewData): number {
  const total = overview.total_monitored || 0;
  if (total === 0) return 100;
  const reachable = overview.reachable || 0;
  const alerting = overview.alerting_devices || 0;
  const interrupted = overview.interrupted_devices || 0;
  const availability = reachable / total;
  const alertRatio = alerting / total;
  const interruptRatio = interrupted / total;
  const score = availability * 60 + (1 - alertRatio) * 30 + (1 - interruptRatio) * 10;
  return Math.round(Math.max(0, Math.min(100, score)));
}


function healthColor(score: number): string {
  if (score >= 90) return '#52c41a';
  if (score >= 70) return '#faad14';
  return '#ff4d4f';
}

export default function StatCards({ overview, loading }: StatCardsProps) {
  const { token } = theme.useToken();

  const total = overview?.total_monitored ?? 0;
  const reachable = overview?.reachable ?? 0;
  const availability = total > 0 ? ((reachable / total) * 100).toFixed(1) : '100.0';
  const activeAlerts = (overview?.alerting_devices ?? 0) + (overview?.crit_alert_devices ?? 0);
  const blindspot = overview?.alert_blindspot ?? 0;
  const healthScore = overview ? calcHealthScore(overview) : 100;

  const kpiStats = [
    {
      title: '监控设备',
      value: total,
      suffix: '台',
      icon: <MonitorOutlined />,
      color: token.colorPrimary,
      bg: 'linear-gradient(135deg, #e6f4ff 0%, #f0f5ff 100%)'
    },
    {
      title: '可用率',
      value: availability,
      suffix: '%',
      icon: <CheckCircleOutlined />,
      color: token.colorSuccess,
      bg: 'linear-gradient(135deg, #f6ffed 0%, #f0f9eb 100%)'
    },
    {
      title: '活跃告警',
      value: activeAlerts,
      suffix: '条',
      icon: <WarningOutlined />,
      color: activeAlerts > 0 ? token.colorError : token.colorSuccess,
      bg:
        activeAlerts > 0
          ? 'linear-gradient(135deg, #fff1f0 0%, #fff0f6 100%)'
          : 'linear-gradient(135deg, #f6ffed 0%, #f0f9eb 100%)'
    },
    {
      title: '告警盲区',
      value: blindspot,
      suffix: '台',
      icon: <EyeInvisibleOutlined />,
      color: blindspot > 0 ? token.colorWarning : token.colorTextSecondary,
      bg: 'linear-gradient(135deg, #fffbe6 0%, #fff7e6 100%)'
    }
  ];

  return (
    <Row gutter={16} align="stretch">
      {kpiStats.map((s) => (
        <Col key={s.title} xs={12} sm={12} md={8} lg={5} xl={5}>
          <Card
            loading={loading}
            variant="borderless"
            style={{
              background: s.bg,
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              transition: 'box-shadow 200ms ease, transform 200ms ease',
              height: '100%'
            }}
            styles={{ body: { padding: 20 } }}
          >
            <Statistic
              title={
                <Text style={{ fontSize: 13, color: token.colorTextSecondary }}>{s.title}</Text>
              }
              value={s.value}
              suffix={s.suffix}
              prefix={<span style={{ color: s.color, marginRight: 8 }}>{s.icon}</span>}
              valueStyle={{
                fontSize: 28,
                fontWeight: 700,
                color: s.color,
                fontFamily: 'Fira Code, monospace'
              }}
            />
          </Card>
        </Col>
      ))}
      {}
      <Col xs={24} sm={12} md={8} lg={4} xl={4}>
        <Card
          loading={loading}
          variant="borderless"
          style={{
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            height: '100%'
          }}
          styles={{ body: { padding: 20 } }}
        >
          <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space direction="vertical" size={2}>
              <Text style={{ fontSize: 13, color: token.colorTextSecondary }}>健康度</Text>
              <span
                style={{
                  fontSize: 28,
                  fontWeight: 700,
                  color: healthColor(healthScore),
                  fontFamily: 'Fira Code, monospace',
                  lineHeight: 1.2
                }}
              >
                {healthScore}
              </span>
              <Link to="/settings/notification-preferences">
                <Button icon={<SettingOutlined />} size="small" type="text">
                  通知配置
                </Button>
              </Link>
            </Space>
            <Progress
              type="circle"
              percent={healthScore}
              size={64}
              strokeColor={healthColor(healthScore)}
              showInfo={false}
            />
          </Space>
        </Card>
      </Col>
    </Row>
  );
}
