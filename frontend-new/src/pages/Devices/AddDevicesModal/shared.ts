/**
 * AddDevicesModal 共享类型、命名工具与常量
 *
 * 从原 AddDevicesModal.tsx 拆出。两个 Tab（BatchAddTab / CloneTab）
 * 均通过本文件获取行类型定义与设备命名/状态展示的纯函数，避免重复实现。
 *
 * 同时收敛 DeviceForm 也需要的共享常量（TYPE_CODE），
 * 消除跨目录重复定义。
 * 注：PORT_TYPE_TEMPLATES 已上提至 @/constants/ports（被 7+ 处消费，不再经本模块重导出）。
 */

import { DEVICE_STATUS_MAP, DEVICE_TYPE_MAP } from '@/types/enums';


export const TYPE_CODE: Record<string, string> = { server: 'SRV', network: 'NET', other: 'OTH' };


export function genBatchName(deviceType: string, index: number): string {
  const code = TYPE_CODE[deviceType] ?? 'DEV';
  const d = new Date();
  const ds = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  return `${code}-${ds}-${String(index).padStart(3, '0')}`;
}


export function extractMaxIndex(names: string[]): number {
  let max = 0;
  for (const name of names) {
    const m = name.match(/-(\d+)$/);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return max;
}

export function genCloneName(baseName: string, index: number): string {
  const m = baseName.match(/^(.*?)(\d+)$/);
  if (m) return `${m[1]}${String(parseInt(m[2], 10) + index).padStart(m[2].length, '0')}`;
  return `${baseName}-${index}`;
}

export function getStatusLabel(code: number): string {
  const e = DEVICE_STATUS_MAP[code as keyof typeof DEVICE_STATUS_MAP];
  return typeof e === 'object' && e && 'label' in e ? e.label : String(e ?? code);
}

export function getStatusColor(code: number): string {
  const e = DEVICE_STATUS_MAP[code as keyof typeof DEVICE_STATUS_MAP];
  return typeof e === 'object' && e && 'color' in e ? e.color : 'default';
}


export function resolveNodeName(
  pattern: string,
  chassisName: string,
  nodeRow?: number,
  nodeCol?: number
): string {
  const nodeCols = 1; 
  const pos = nodeRow && nodeCol ? (nodeRow - 1) * nodeCols + nodeCol : 0;
  return pattern
    .replace('{chassis}', chassisName)
    .replace('{pos}', String(pos))
    .replace('{row}', String(nodeRow ?? ''))
    .replace('{col}', String(nodeCol ?? ''));
}


export interface DeviceBatchRow {
  key: string;
  device_name: string;
  device_model?: string;
  serial_number: string;
  u_position: number | null;
  height_u: number;
  status: number;
  
  node_rows?: number;
  
  node_cols?: number;
  
  parent_device_id?: number;
  
  node_row?: number;
  
  node_col?: number;
}


export const STATUS_OPTIONS = Object.entries(DEVICE_STATUS_MAP).map(([k, v]) => ({
  value: Number(k),
  label: typeof v === 'object' && v && 'label' in v ? v.label : String(v)
}));

export const TYPE_OPTIONS = Object.entries(DEVICE_TYPE_MAP).map(([k, v]) => ({
  label: v.label,
  value: k
}));
