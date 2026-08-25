/**
 * 监控总览 - 协议分布环形饼图
 *
 * 纯前端组件，数据来自 useMonitorOverview() 的 by_protocol。
 * 空数据（dict 为空）时渲染 Empty，避免 @ant-design/charts 空白/报错。
 */
import { useMemo } from 'react';
import { Card, Empty, theme } from 'antd';
import { Pie } from '@ant-design/charts';
import { MONITOR_PROTOCOL_PALETTE } from '@/types/enums';

const { useToken } = theme;

interface ProtocolPieProps {
  data: Record<string, number> | undefined;
  total: number | undefined;
  loading?: boolean;
}

export default function ProtocolPie({ data, total, loading }: ProtocolPieProps) {
  const { token } = useToken();

  const chartData = useMemo(
    () =>
      (data ? Object.entries(data) : [])
        .filter(([, value]) => value > 0)
        .map(([name, value]) => ({
          name,
          value,
          color: MONITOR_PROTOCOL_PALETTE[name] ?? token.colorTextSecondary
        })),
    [data, token.colorTextSecondary]
  );

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
          content: '协议总数',
          style: { fontSize: '12px', color: token.colorTextSecondary, lineHeight: '16px' }
        },
        content: {
          style: { fontSize: '24px', fontWeight: 700, color: token.colorText, lineHeight: '30px' },
          formatter: () => `${total ?? 0}`
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
      title="协议分布"
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
