
export const MIN_SCALE = 0.4;
export const MAX_SCALE = 1.6;

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export function scrollForZoom(
  scroll: number,
  pointer: number,
  scale: number,
  nextScale: number
): number {
  return ((scroll + pointer) * nextScale) / scale - pointer;
}

export function toScaleTransform(scale: number): string {
  return `scale(${scale})`;
}
