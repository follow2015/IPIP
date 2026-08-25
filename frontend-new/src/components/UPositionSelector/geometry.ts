
import type { OccupiedPosition } from './types';

export function uToTop(u: number, unit: number): number {
  return (u - 1) * unit;
}

export function displayLabel(internalU: number, totalU: number): number {
  return totalU - internalU + 1;
}

export function internalToPhysical(internalU: number, totalU: number): number {
  return totalU - internalU + 1;
}

export function physicalToInternal(physicalU: number, totalU: number): number {
  return totalU - physicalU + 1;
}

export function checkConflict(
  devices: OccupiedPosition[],
  skipId: number,
  start: number,
  size: number
): boolean {
  for (const d of devices) {
    if (d.deviceId === skipId) continue;
    for (let u = start; u < start + size; u++) {
      if (u >= d.uPosition && u < d.uPosition + d.uSize) return true;
    }
  }
  return false;
}
