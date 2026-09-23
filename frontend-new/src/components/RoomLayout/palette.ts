import type { GlobalToken } from 'antd';
import type { TFunction } from 'i18next';
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


export type ChannelTypeKey =
  | 'roomLayout.channelType.cold'
  | 'roomLayout.channelType.hot'
  | 'roomLayout.channelType.mixed';

export const CHANNEL_TYPE_LABEL_KEYS: Record<string, ChannelTypeKey> = {
  cold: 'roomLayout.channelType.cold',
  hot: 'roomLayout.channelType.hot',
  mixed: 'roomLayout.channelType.mixed'
};

export type SupplyKey =
  | 'roomLayout.supply.floor'
  | 'roomLayout.supply.direct'
  | 'roomLayout.supply.none';

export const SUPPLY_LABEL_KEYS: Record<string, SupplyKey> = {
  floor: 'roomLayout.supply.floor',
  direct: 'roomLayout.supply.direct',
  none: 'roomLayout.supply.none'
};

export type ChannelPaletteKey = 'blue' | 'orange' | 'gold';

export function paletteKeyOf(channelType: string): ChannelPaletteKey {
  if (channelType === 'cold') return 'blue';
  if (channelType === 'hot') return 'orange';
  return 'gold';
}


export const MARKER_TYPE_LABEL_KEYS: Record<string, MarkerTypeKey> = {
  ac: 'roomLayout.markerType.ac',
  pdu: 'roomLayout.markerType.pdu',
  pillar: 'roomLayout.markerType.pillar',
  door: 'roomLayout.markerType.door',
  other: 'roomLayout.markerType.other'
};

export type MarkerTypeKey =
  | 'roomLayout.markerType.ac'
  | 'roomLayout.markerType.pdu'
  | 'roomLayout.markerType.pillar'
  | 'roomLayout.markerType.door'
  | 'roomLayout.markerType.other';

export function positionLabel(row: number, col: number, t: TFunction<'asset'>): string {
  const rowText = row === 0 ? t('roomLayout.outsideRow') : t('roomLayout.positionRow', { row });
  const colText = col === 0 ? t('roomLayout.outsideCol') : t('roomLayout.positionCol', { col });
  return `${rowText} ${colText}`;
}
