/**
 * portStatus — 端口状态工具函数
 *
 * 从 PortActions 和 SwitchDetail 提取的共用逻辑，消除重复定义。
 * 标签/颜色统一取自 enums.ts 的 LINK_STATUS_MAP，保证跨页一致。
 */

import type { TFunction } from 'i18next';
import { LINK_STATUS_MAP } from '@/types/enums';
import { getLinkStatusMeta } from '@/types/statusMeta';
import type { DeviceT } from '@/types/statusMeta';

export function getStatusLabel(status: string | null | undefined, t: DeviceT): string {
  const lower = (status || '').toLowerCase();
  if (lower === 'admin_down' || lower.includes('administratively') || lower === '*down') {
    return getLinkStatusMeta('admin_down', t)?.label ?? (status || '');
  }
  return getLinkStatusMeta(lower, t)?.label ?? (status || '');
}

/**
 * 端口状态 → Ant Design Tag 预设色名
 * 使用内置预设色，自动处理背景与文字对比度。
 */
export function getStatusTagPreset(status: string | null | undefined): string {
  const lower = (status || '').toLowerCase();
  if (lower === 'admin_down' || lower.includes('administratively') || lower === '*down') {
    return LINK_STATUS_MAP.admin_down.color;
  }
  return LINK_STATUS_MAP[lower]?.color ?? 'default';
}

export function isAdminDown(status: string | null | undefined): boolean {
  const lower = (status || '').toLowerCase();
  return lower === 'admin_down' || lower.includes('administratively') || lower === '*down';
}

export function extractErrorMessage(err: unknown, t: TFunction<'common'>): string {
  if (err instanceof Error) {
    const axiosErr = err as { response?: { data?: { message?: string } } };
    const backendMsg = axiosErr?.response?.data?.message;
    return backendMsg || err.message;
  }
  return t('message.operationFailed');
}
