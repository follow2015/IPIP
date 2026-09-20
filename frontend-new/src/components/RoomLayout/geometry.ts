import type { Cabinet, RoomLayoutMarker } from '@/types/models';

export const BAND_WIDTH_RATIO = 0.25;

export interface CellMetrics {
  cellWidth: number;
  cellHeight: number;
  gap: number;
}

export function cellLeft(col: number, cellWidth: number, gap: number): number {
  return (col - 1) * (cellWidth + gap);
}

export function cellTop(row: number, cellHeight: number, gap: number): number {
  return (row - 1) * (cellHeight + gap);
}

export function gridWidth(maxCol: number, cellWidth: number, gap: number): number {
  return maxCol * (cellWidth + gap) - gap;
}

export function gridHeight(maxRow: number, cellHeight: number, gap: number): number {
  return maxRow * (cellHeight + gap) - gap;
}

export function pointToCell(
  x: number,
  y: number,
  metrics: CellMetrics
): { row: number; col: number } | null {
  if (x < 0 || y < 0) return null;
  const { cellWidth, cellHeight, gap } = metrics;
  return {
    col: Math.floor(x / (cellWidth + gap)) + 1,
    row: Math.floor(y / (cellHeight + gap)) + 1
  };
}

export function bandLeft(
  col_number: number,
  cellWidth: number,
  gap: number,
  bandWidth: number
): number {
  return cellLeft(col_number, cellWidth, gap) + cellWidth + gap / 2 - bandWidth / 2;
}

export function isPositioned(cabinet: Cabinet): boolean {
  return cabinet.row != null && cabinet.col != null && cabinet.row > 0 && cabinet.col > 0;
}

export function groupCabinetsByCell(cabinets: Cabinet[]): Map<string, Cabinet[]> {
  const map = new Map<string, Cabinet[]>();
  for (const cabinet of cabinets) {
    if (!isPositioned(cabinet)) continue;
    const key = `${cabinet.row},${cabinet.col}`;
    const list = map.get(key);
    if (list) {
      list.push(cabinet);
    } else {
      map.set(key, [cabinet]);
    }
  }
  return map;
}


export function isMarkerPositioned(marker: RoomLayoutMarker): boolean {
  return (
    marker.row_number != null &&
    marker.col_number != null &&
    marker.row_number >= 0 &&
    marker.col_number >= 0
  );
}

export interface GridBounds {
  minRow: number;
  minCol: number;
  maxRow: number;
  maxCol: number;
  rows: number;
  cols: number;
}

export function gridBounds(cabinets: Cabinet[], markers: RoomLayoutMarker[]): GridBounds {
  let minRow = 1;
  let minCol = 1;
  let maxRow = 0;
  let maxCol = 0;

  for (const cabinet of cabinets) {
    if (!isPositioned(cabinet)) continue;
    maxRow = Math.max(maxRow, cabinet.row!);
    maxCol = Math.max(maxCol, cabinet.col!);
  }

  for (const marker of markers) {
    if (!isMarkerPositioned(marker)) continue;
    minRow = Math.min(minRow, marker.row_number);
    minCol = Math.min(minCol, marker.col_number);
    maxRow = Math.max(maxRow, marker.row_number);
    maxCol = Math.max(maxCol, marker.col_number);
  }

  return {
    minRow,
    minCol,
    maxRow,
    maxCol,
    rows: maxRow >= minRow ? maxRow - minRow + 1 : 0,
    cols: maxCol >= minCol ? maxCol - minCol + 1 : 0
  };
}
