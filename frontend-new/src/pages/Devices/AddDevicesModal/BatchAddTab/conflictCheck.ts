/**
 * BatchAddTab 提交前的纯函数冲突预检查
 *
 * 从原单体 BatchAddTab 的 handleSubmit 内联校验中抽离，
 * 不依赖任何 React 状态，便于单元测试与复用（CloneTab 后续可复用 U 位冲突检查）。
 */

import type { DeviceBatchRow } from '../shared';


export function checkUConflict(rowsToCheck: DeviceBatchRow[]): string | null {
  const withU = rowsToCheck.filter((r) => r.u_position != null);
  
  const sorted = [...withU].sort((a, b) => (a.u_position ?? 0) - (b.u_position ?? 0));
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i];
    const b = sorted[i + 1];
    const aEnd = (a.u_position ?? 0) + (a.height_u ?? 1);
    if ((b.u_position ?? 0) < aEnd) {
      return `U位冲突：「${a.device_name}」(U${a.u_position}, 高${a.height_u ?? 1}U) 与「${b.device_name}」(U${b.u_position}) 重叠`;
    }
  }
  return null;
}


export function checkNodePositionConflict(rowsToCheck: DeviceBatchRow[]): string | null {
  const seen = new Map<string, string>();
  for (const r of rowsToCheck) {
    if (r.node_row == null || r.node_col == null) continue;
    const key = `${r.node_row}-${r.node_col}`;
    if (seen.has(key)) {
      return `节点位置冲突：「${seen.get(key)}」与「${r.device_name}」都填了 行${r.node_row}列${r.node_col}`;
    }
    seen.set(key, r.device_name);
  }
  return null;
}
