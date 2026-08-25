/**
 * useUPositionAssigner — U 位自动分配
 *
 * 原问题：handleAutoAssignUPositions 在 BatchAddDeviceModal 和
 * QuickCloneDeviceModal 中逐字复制，逻辑完全相同。
 * 本文件将算法提取为纯函数 assignUPositions + 便捷 Hook。
 *
 * 用法（Hook 形式）：
 *   const { assign } = useUPositionAssigner(availableUPositions);
 *   const updated = assign(rows);   // 返回已分配 u_position 的新行数组
 *
 * 用法（纯函数形式，测试友好）：
 *   const updated = assignUPositions(rows, availablePositions);
 */
import { useCallback } from 'react';


export interface UPositionRow {
  key: string;
  
  height_u?: number | null;
  
  u_position: number | null;
}


export function assignUPositions<T extends UPositionRow>(
  rows: T[],
  availablePositions: number[],
  gap: number = 0,
): T[] {
  if (!availablePositions.length) return rows;

  const sorted = [...availablePositions].sort((a, b) => a - b);
  let posIndex = 0;

  return rows.map((row, rowIndex) => {
    const heightU = row.height_u ?? 1;

    for (let j = posIndex; j <= sorted.length - heightU; j++) {
      const start = sorted[j];
      let continuous = true;

      for (let k = 1; k < heightU; k++) {
        if (sorted[j + k] !== start + k) {
          continuous = false;
          break;
        }
      }

      if (continuous) {
        
        posIndex = j + heightU + (rowIndex < rows.length - 1 ? gap : 0);
        return { ...row, u_position: start };
      }
    }

    
    return row;
  });
}


export function useUPositionAssigner(availablePositions: number[] | undefined) {
  const assign = useCallback(
    <T extends UPositionRow>(rows: T[], gap: number = 0): T[] => {
      if (!availablePositions?.length) return rows;
      return assignUPositions(rows, availablePositions, gap);
    },
    [availablePositions],
  );

  return { assign, available: availablePositions?.length ?? 0 };
}
