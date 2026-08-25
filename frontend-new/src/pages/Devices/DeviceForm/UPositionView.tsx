/**
 * UPositionView — 机柜 U 位方块网格视图
 *
 * 从原 DeviceForm.tsx 拆出。纯展示组件：接收机柜布局数据，渲染 U 位方块
 * 网格 + 图例，不含任何表单/请求逻辑，可独立复用与测试。
 */

import { useMemo } from 'react';
import { Tooltip } from 'antd';

type UBlockStatus = 'available' | 'occupied' | 'current';

export default function UPositionView({ layout, currentU, currentHeightU }: {
  layout: {
    total_u: number;
    used_u: number;
    u_map: Record<number, {
      device_id: number;
      device_name: string;
      device_type: string;
      is_start: boolean;
      height_u: number;
      power: number | null;
    }>;
  } | null | undefined;
  currentU?: number | null;
  currentHeightU?: number | null;
}) {
  const currentUSet = useMemo(() => {
    const set = new Set<number>();
    if (currentU && currentHeightU) {
      for (let i = currentU; i < currentU + currentHeightU; i++) {
        set.add(i);
      }
    }
    return set;
  }, [currentU, currentHeightU]);

  if (!layout) return null;
  const { total_u, u_map } = layout;

  const getBlockStatus = (u: number): UBlockStatus => {
    if (currentUSet.has(u)) return 'current';
    if (u_map[u]) return 'occupied';
    return 'available';
  };

  const statusColors: Record<UBlockStatus, { bg: string; border: string; text: string }> = {
    available: { bg: '#f6ffed', border: '#b7eb8f', text: '#52c41a' },
    occupied: { bg: '#fff1f0', border: '#ffa39e', text: '#f5222d' },
    current: { bg: '#fffbe6', border: '#ffe58f', text: '#faad14' },
  };

  return (
    <div style={{
      marginTop: 8,
      padding: '8px 12px',
      background: '#fafafa',
      borderRadius: 6,
      border: '1px solid #f0f0f0',
    }}>
      {/* 图例 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 12, alignItems: 'center' }}>
        <span style={{ color: '#8c8c8c' }}>U位视图：</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 2, background: statusColors.available.bg, border: `1px solid ${statusColors.available.border}` }} />
          <span>可分配</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 2, background: statusColors.occupied.bg, border: `1px solid ${statusColors.occupied.border}` }} />
          <span>已分配</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 2, background: statusColors.current.bg, border: `1px solid ${statusColors.current.border}` }} />
          <span>当前分配</span>
        </span>
      </div>

      {/* 方块网格：从 U1 开始逐行排列 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
        {Array.from({ length: total_u }, (_, i) => i + 1).map(u => {
          const status = getBlockStatus(u);
          const color = statusColors[status];
          const info = u_map[u];
          const tooltip = info?.is_start
            ? `${info.device_name} (U${u}~U${u + info.height_u - 1})`
            : status === 'current'
              ? `当前设备 U${u}`
              : `U${u} 可分配`;

          return (
            <Tooltip key={u} title={tooltip}>
              <div style={{
                width: 28,
                height: 28,
                borderRadius: 3,
                background: color.bg,
                border: `1px solid ${color.border}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 500,
                color: color.text,
                cursor: 'default',
              }}>
                {u}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}
