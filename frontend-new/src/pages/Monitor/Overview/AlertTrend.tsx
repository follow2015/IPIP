/**
 * 监控总览 - 告警趋势条形图（G10 时间范围对比）
 *
 * 从 Overview 拆分（M28）：按日聚合告警数，简易柱状无外部图表依赖。
 */
import { useState, useMemo } from 'react';
import { Card, Empty, Space, Tooltip, Typography, DatePicker, theme } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { ensureUtc } from '@/utils/format';
import { useMonitorAlerts } from '@/services/monitor';

const { Text } = Typography;

export default function AlertTrend() {
  const { token } = theme.useToken();
  const [trendRange, setTrendRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(6, 'day'),
    dayjs()
  ]);
  const { data: trendAlerts } = useMonitorAlerts({
    start_date: trendRange[0].toISOString(),
    end_date: trendRange[1].toISOString(),
    per_page: 200
  });

  const trendByDay = useMemo(() => {
    const items = trendAlerts?.items ?? [];
    const map = new Map<string, number>();
    for (const it of items) {
      if (!it.created_at) continue;
      const day = dayjs(ensureUtc(it.created_at)).format('YYYY-MM-DD');
      map.set(day, (map.get(day) ?? 0) + 1);
    }
    const days: { day: string; count: number }[] = [];
    let cur = trendRange[0].clone();
    while (cur.isBefore(trendRange[1]) || cur.isSame(trendRange[1], 'day')) {
      const key = cur.format('YYYY-MM-DD');
      days.push({ day: key, count: map.get(key) ?? 0 });
      cur = cur.add(1, 'day');
    }
    return days;
  }, [trendAlerts, trendRange]);

  const trendMax = Math.max(1, ...trendByDay.map((d) => d.count));

  return (
    <Card
      title="告警趋势"
      variant="borderless"
      style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
      extra={
        <Space>
          <DatePicker.RangePicker
            value={trendRange}
            onChange={(v) => {
              if (v && v[0] && v[1]) setTrendRange([v[0], v[1]]);
            }}
            presets={[
              { label: '今日', value: [dayjs(), dayjs()] as [Dayjs, Dayjs] },
              { label: '近 7 天', value: [dayjs().subtract(6, 'day'), dayjs()] as [Dayjs, Dayjs] },
              { label: '近 30 天', value: [dayjs().subtract(29, 'day'), dayjs()] as [Dayjs, Dayjs] }
            ]}
            size="small"
          />
        </Space>
      }
    >
      {trendByDay.length === 0 ? (
        <Empty description="所选时间范围无告警" />
      ) : (
        <div
          style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 120, padding: '8px 0' }}
        >
          {trendByDay.map((d) => (
            <Tooltip key={d.day} title={`${d.day}：${d.count} 条`}>
              <div
                style={{
                  flex: 1,
                  minWidth: 8,
                  height: `${(d.count / trendMax) * 100}%`,
                  minHeight: d.count > 0 ? 4 : 2,
                  background: d.count > 0 ? token.colorPrimary : token.colorFillSecondary,
                  borderRadius: 2,
                  transition: 'height 0.3s'
                }}
              />
            </Tooltip>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {trendRange[0].format('YYYY-MM-DD')}
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          共 {trendByDay.reduce((s, d) => s + d.count, 0)} 条告警
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {trendRange[1].format('YYYY-MM-DD')}
        </Text>
      </div>
    </Card>
  );
}
