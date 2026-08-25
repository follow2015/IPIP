/**
 * 监控总览 - 状态分布环形饼图（5 维）
 *
 * 数据来自 useMonitorOverview() 的统计字段：
 * 可达 / 不可达 / 抖动中 / 从未可达 / 告警盲区。
 * 空数据（全为 0）时渲染 Empty。
 */
import { useMemo } from 'react';
import { Card, Empty, theme } from 'antd';
import { Pie } from '@ant-design/charts';

const { useToken } = theme;

interface StatusPieProps {
  reachable: number | undefined;
  unreachable: number | undefined;
  flapping: number | undefined;
  neverReachable: number | undefined;
  alertBlindspot: number | undefined;
  loading?: boolean;
}

export default function StatusPie({
  reachable,
  unreachable,
  flapping,
  neverReachable,
  alertBlindspot,
  loading
}: StatusPieProps) {
  const { token } = useToken();

  const chartData = useMemo(() => {
    const base = [
      { name: '可达', value: reachable ?? 0, color: token.colorSuccess },
      { name: '不可达', value: unreachable ?? 0, color: token.colorError },
      { name: '抖动中', value: flapping ?? 0, color: token.colorWarning },
      { name: '从未可达', value: neverReachable ?? 0, color: token.colorTextDisabled },
      { name: '告警盲区', value: alertBlindspot ?? 0, color: token.colorErrorActive }
    ];
    return base.filter((d) => d.value > 0);
  }, [reachable, unreachable, flapping, neverReachable, alertBlindspot, token]);

  const total = useMemo(() => chartData.reduce((s, d) => s + d.value, 0), [chartData]);
  const isEmpty = chartData.length === 0;

  const config = useMemo(
    () => ({
      appendPadding: [8, 8, 8, 8] as [number, number, number, number],
      data: isEmpty ? [{ name: '暂无数据', value: 1, color: token.colorBgContainer }] : chartData,
      angleField: 'value',
      colorField: 'name',
      color: isEmpty ? [token.colorBgContainer] : chartData.map((d) => d.color),
      radius: 0.8,
      innerRadius: 0.6,
      label: { type: 'outer' as const },
      tooltip: {
        title: 'name',
        items: [{ field: 'value', name: '数量' }]
      },
      statistic: {
        title: {
          content: '设备总数',
          style: { fontSize: '12px', color: token.colorTextSecondary, lineHeight: '16px' }
        },
        content: {
          style: { fontSize: '24px', fontWeight: 700, color: token.colorText, lineHeight: '30px' },
          formatter: () => `${total}`
        }
      },
      legend: {
        position: 'bottom' as const,
        layout: 'horizontal' as const,
        label: { style: { fontSize: 11, fill: token.colorTextSecondary } }
      },
      interactions: [{ type: 'element-active' }],
      animation: { appear: { duration: 600, easing: 'easeQuadOut' } },
      pieStyle: { lineWidth: 2, stroke: token.colorBgElevated }
    }),
    [chartData, isEmpty, total, token]
  );

  return (
    <Card
      title="状态分布"
      size="small"
      loading={loading}
      variant="borderless"
      style={{ height: '100%' }}
    >
      {isEmpty ? (
        <Empty description="暂无数据" style={{ padding: '48px 0' }} />
      ) : (
        <Pie {...config} height={260} />
      )}
    </Card>
  );
}
