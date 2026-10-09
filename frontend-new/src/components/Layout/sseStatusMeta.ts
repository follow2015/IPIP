import type { BadgeProps } from 'antd';
import type { SSEStatus } from '@/hooks/useSSEConnection';

export const SSE_BADGE_STATUS: Record<SSEStatus, BadgeProps['status']> = {
  idle: 'default',
  connecting: 'processing',
  live: 'success',
  degraded: 'warning'
};

export const SSE_VISIBLE_STATUSES: readonly SSEStatus[] = ['connecting', 'live', 'degraded'];

export function isSSEStatusVisible(status: SSEStatus): boolean {
  return SSE_VISIBLE_STATUSES.includes(status);
}

export const SSE_STATUS_KEY = {
  idle: 'realtime.status.idle',
  connecting: 'realtime.status.connecting',
  live: 'realtime.status.live',
  degraded: 'realtime.status.degraded'
} as const satisfies Record<SSEStatus, string>;

export const SSE_STATUS_SHORT_KEY = {
  idle: 'realtime.status.idleShort',
  connecting: 'realtime.status.connectingShort',
  live: 'realtime.status.liveShort',
  degraded: 'realtime.status.degradedShort'
} as const satisfies Record<SSEStatus, string>;
