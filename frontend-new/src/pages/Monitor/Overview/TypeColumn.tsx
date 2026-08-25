/**
 * 监控总览 - 设备类型分布柱状图
 *
 * 纯前端组件，数据来自 useMonitorOverview() 的 by_device_type。
 * 空数据（dict 为空）时渲染 Empty。
 */
import { useMemo } from 'react';
import { Card, Empty, theme } from 'antd';
import { Column } from '@ant-design/charts';

const { useToken } = theme;

interface TypeColumnProps {
  data: Record<string, number> | undefined;
  loading?: boolean;
}

export default function TypeColumn({ data, loading }: TypeColumnProps) {
  const { token } = useToken();

  const chartData = useMemo(
    () => (data ? Object.entries(data) : []).map(([type, count]) => ({ type, count })),
    [data]
  );

  const isEmpty = chartData.length === 0;

  const config = useMemo(
    () => ({
      data: chartData,
      xField: 'type',
      yField: 'count',
      color: token.colorPrimary,
      columnWidthRatio: 0.6,
      label: { position: 'top' as const },
      tooltip: {
        title: 'type',
        items: [{ field: 'count', name: '数量' }]
      },
      axis: {
        x: {
          label: { style: { fontSize: 11, fill: token.colorTextSecondary } },
          line: { style: { stroke: token.colorBorderSecondary } }
        },
        y: {
          label: { style: { fontSize: 11, fill: token.colorTextSecondary } },
          grid: { line: { style: { stroke: token.colorBorderSecondary } } }
        }
      },
      legend: false,
      interactions: [{ type: 'element-active' }],
      animation: { appear: { duration: 600, easing: 'easeQuadOut' } }
    }),
    [chartData, token]
  );

  return (
    <Card
      title="设备类型分布"
      size="small"
      loading={loading}
      variant="borderless"
      style={{ height: '100%' }}
    >
      {isEmpty ? (
        <Empty description="暂无数据" style={{ padding: '48px 0' }} />
      ) : (
        <Column {...config} height={260} />
      )}
    </Card>
  );
}
