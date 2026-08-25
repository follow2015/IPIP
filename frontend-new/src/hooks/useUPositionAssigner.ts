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

/**
 * 纯函数：为行列表自动分配 U 位
 *
 * 算法：
 *   1. 对 availablePositions 升序排序
 *   2. 逐行寻找满足 height_u 连续空间的起始位置
 *   3. 找到后消费该空间段（更新 posIndex 跳过已分配位置 + gap 间隔）
 *   4. 无法满足时保留原行不修改（不强制覆盖）
 *
 * @param rows               需要分配的行列表（只读）
 * @param availablePositions 可用 U 位列表（无需预排序）
 * @param gap                设备间U位间隔（默认0，即紧密排列）
 * @returns                  分配后的新行列表（未修改原数组）
 */
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

/**
 * Hook 形式：绑定 availablePositions 后返回 assign 方法
 * 当 availablePositions 为空时，assign 返回原数组，调用方可据此判断是否提示用户
 *
 * @param availablePositions 可用 U 位列表（来自 useCabinetAvailableUPositions）
 */
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
