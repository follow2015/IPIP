/**
 * BatchAddTab 提交前的纯函数冲突预检查
 *
 * 从原单体 BatchAddTab 的 handleSubmit 内联校验中抽离，
 * 不依赖任何 React 状态，便于单元测试与复用（CloneTab 后续可复用 U 位冲突检查）。
 */

import type { DeviceBatchRow } from '../shared';
import type { DeviceT } from '@/types/statusMeta';

export function checkUConflict(rowsToCheck: DeviceBatchRow[], t: DeviceT): string | null {
  const withU = rowsToCheck.filter((r) => r.u_position != null);
  const sorted = [...withU].sort((a, b) => (a.u_position ?? 0) - (b.u_position ?? 0));
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i];
    const b = sorted[i + 1];
    const aEnd = (a.u_position ?? 0) + (a.height_u ?? 1);
    if ((b.u_position ?? 0) < aEnd) {
      return t('addModal.conflict.u', {
        nameA: a.device_name,
        uA: a.u_position,
        heightA: a.height_u ?? 1,
        nameB: b.device_name,
        uB: b.u_position
      });
    }
  }
  return null;
}

/**
 * 节点模式：检查同批次内行号+列号是否重复。
 * @returns 冲突描述字符串；无冲突返回 null
 */
export function checkNodePositionConflict(
  rowsToCheck: DeviceBatchRow[],
  t: DeviceT
): string | null {
  const seen = new Map<string, string>();
  for (const r of rowsToCheck) {
    if (r.node_row == null || r.node_col == null) continue;
    const key = `${r.node_row}-${r.node_col}`;
    if (seen.has(key)) {
      return t('addModal.conflict.nodePosition', {
        nameA: seen.get(key),
        nameB: r.device_name,
        row: r.node_row,
        col: r.node_col
      });
    }
    seen.set(key, r.device_name);
  }
  return null;
}
