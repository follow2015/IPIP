import type { GlobalToken } from 'antd';
import { CabinetStatusCode } from '@/types/enums';

export type StatusPaletteKey = 'red' | 'green' | 'blue' | 'orange' | 'purple';

export interface StatusPalette {
  bg: string;
  accent: string;
  border: string;
  text: string;
}

export const DEFAULT_STATUS = CabinetStatusCode.AVAILABLE;

export const STATUS_PALETTE_KEYS: Record<number, StatusPaletteKey> = {
  [CabinetStatusCode.DISABLED]: 'red',
  [CabinetStatusCode.AVAILABLE]: 'green',
  [CabinetStatusCode.IN_USE]: 'blue',
  [CabinetStatusCode.MAINTENANCE]: 'orange',
  [CabinetStatusCode.RESERVED]: 'purple'
};

export function getStatusPalette(token: GlobalToken, status: number): StatusPalette {
  const key = STATUS_PALETTE_KEYS[status] ?? 'blue';
  return {
    bg: token[`${key}1`],
    accent: token[`${key}5`],
    border: token[`${key}6`],
    text: token[`${key}7`]
  };
}


export const CHANNEL_TYPE_LABEL: Record<string, string> = {
  cold: '冷通道',
  hot: '热通道',
  mixed: '混合通道'
};

export const SUPPLY_LABEL: Record<string, string> = {
  floor: '地板下送风',
  direct: '上送风直吹（非推荐）',
  none: '无'
};

export type ChannelPaletteKey = 'blue' | 'orange' | 'gold';

export function paletteKeyOf(channelType: string): ChannelPaletteKey {
  if (channelType === 'cold') return 'blue';
  if (channelType === 'hot') return 'orange';
  return 'gold';
}


export const MARKER_TYPE_LABEL: Record<string, string> = {
  ac: '空调',
  pdu: 'PDU',
  pillar: '立柱',
  door: '门',
  other: '其他'
};

export function positionLabel(row: number, col: number): string {
  const rowText = row === 0 ? '第 1 行外侧' : `第 ${row} 行`;
  const colText = col === 0 ? '第 1 列外侧' : `第 ${col} 列`;
  return `${rowText} ${colText}`;
}
