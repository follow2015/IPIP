/**
 * PortStats — 占用状态统计标签（SSH / 手动模式共用）
 */
import { Tag } from 'antd';
import { PORT_USAGE_STATUS_MAP } from '@/types/enums';

export function PortStats({ portStats }: { portStats: Record<string, number> }) {
  return (
    <>
      {Object.entries(portStats).map(([status, count]) => {
        const cfg = PORT_USAGE_STATUS_MAP[status];
        return (
          <Tag key={status} color={cfg?.color ?? 'default'}>
            {cfg?.label ?? status}: {count}
          </Tag>
        );
      })}
    </>
  );
}
