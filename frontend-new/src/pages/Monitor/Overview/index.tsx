/**
 * 监控中心 - 总览页
 *
 * 重构（M29）：三段式布局，突出核心信息层次。
 *
 * 1. KPI 概览区：4 核心 KPI 卡片 + 健康度仪表盘（StatCards）
 * 2. 告警趋势 + 分布区：AlertTrend + 协议/类型/状态分布并列
 * 3. 异常聚焦区：异常设备表 + 最近告警（含快捷操作）左右分栏
 *
 * 数据每 30s 自动刷新（TanStack Query refetchInterval）。
 */
import { Row, Col } from 'antd';
import { useMonitorOverview } from '@/services/monitor';
import ProtocolPie from './ProtocolPie';
import TypeColumn from './TypeColumn';
import StatusPie from './StatusPie';
import StatCards from './StatCards';
import AlertTrend from './AlertTrend';
import RecentAlerts from './RecentAlerts';
import DeviceStatusTable from './DeviceStatusTable';

export default function MonitorOverview() {
  const { data: overview, isLoading: overviewLoading } = useMonitorOverview();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {}
      <StatCards overview={overview} loading={overviewLoading} />

      {}
      <AlertTrend />
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <ProtocolPie
            data={overview?.by_protocol}
            total={overview?.total_monitored}
            loading={overviewLoading}
          />
        </Col>
        <Col xs={24} md={8}>
          <TypeColumn data={overview?.by_device_type} loading={overviewLoading} />
        </Col>
        <Col xs={24} md={8}>
          <StatusPie
            reachable={overview?.reachable}
            unreachable={overview?.unreachable}
            flapping={overview?.flapping}
            neverReachable={overview?.never_reachable}
            alertBlindspot={overview?.alert_blindspot}
            loading={overviewLoading}
          />
        </Col>
      </Row>

      {}
      <RecentAlerts loading={overviewLoading} />

      {}
      <DeviceStatusTable />
    </div>
  );
}
