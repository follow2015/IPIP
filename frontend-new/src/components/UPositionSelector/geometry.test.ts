import { describe, it, expect } from 'vitest';
import {
  physicalToInternal,
  internalToPhysical,
  displayLabel,
  checkConflict
} from '@/components/UPositionSelector/geometry';
import { computeLayout, computeBlockInfoVisibility } from '@/components/UPositionSelector/layout';
import type { OccupiedPosition } from '@/components/UPositionSelector/types';

describe('geometry 坐标换算', () => {
  const totalU = 42;

  it('physicalToInternal / internalToPhysical 互为逆运算', () => {
    expect(physicalToInternal(1, totalU)).toBe(totalU); // 物理U1(底部) → 内部坐标42(底部)
    expect(internalToPhysical(totalU, totalU)).toBe(1);
    for (let u = 1; u <= totalU; u++) {
      expect(internalToPhysical(physicalToInternal(u, totalU), totalU)).toBe(u);
    }
  });

  it('displayLabel 底部=U1 顶部=U42', () => {
    expect(displayLabel(1, totalU)).toBe(totalU);
    expect(displayLabel(totalU, totalU)).toBe(1);
  });
});

describe('checkConflict 占位冲突', () => {
  const devices: OccupiedPosition[] = [
    { uPosition: 5, uSize: 2, deviceId: 1, deviceName: 'A' },
    { uPosition: 10, uSize: 3, deviceId: 2, deviceName: 'B' }
  ];

  it('重叠返回 true', () => {
    expect(checkConflict(devices, 99, 6, 2)).toBe(true); // 覆盖 A(5-6)
  });

  it('不重叠返回 false', () => {
    expect(checkConflict(devices, 99, 1, 2)).toBe(false); // 1-2 空闲
  });

  it('跳过自身设备', () => {
    expect(checkConflict(devices, 1, 5, 2)).toBe(false); // 与自身重叠应忽略
  });
});

describe('layout 响应式计算', () => {
  it('不同容器宽度给出不同行高/面板开关', () => {
    const xs = computeLayout(200);
    const lg = computeLayout(800);
    expect(xs.rowH).toBeLessThan(lg.rowH);
    expect(xs.showSidePanel).toBe(false);
    expect(lg.showSidePanel).toBe(true);
  });

  it('computeBlockInfoVisibility 随高度/宽度递增信息行', () => {
    const none = computeBlockInfoVisibility(20, 50, 28);
    const all = computeBlockInfoVisibility(200, 300, 28);
    expect(none.showInfoLine).toBe(false);
    expect(all.showInfoLine && all.showModelLine && all.showSnLine).toBe(true);
  });
});
