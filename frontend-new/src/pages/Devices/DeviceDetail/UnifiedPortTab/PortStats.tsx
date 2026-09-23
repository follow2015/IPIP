/**
 * PortStats — 占用状态统计标签（SSH / 手动模式共用）
 */
import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { getPortUsageMeta } from '@/types/statusMeta';

export function PortStats({ portStats }: { portStats: Record<string, number> }) {
  const { t } = useTranslation('device');
  return (
    <>
      {Object.entries(portStats).map(([status, count]) => {
        const cfg = getPortUsageMeta(status, t);
        return (
          <Tag key={status} color={cfg?.color ?? 'default'}>
            {cfg?.label ?? status}: {count}
          </Tag>
        );
      })}
    </>
  );
}
