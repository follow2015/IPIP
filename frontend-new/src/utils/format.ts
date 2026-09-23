/**
 * 格式化工具
 * - 日期/数字/容量格式化
 */
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import type { TFunction } from 'i18next';
import { PROBE_ERROR_MAP, ProbeErrorCode } from '@/types/enums';
import { getProbeErrorMeta, type DeviceT } from '@/types/statusMeta';

dayjs.extend(utc);

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

export function ensureUtc(iso: string): string {
  if (iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso)) return iso;
  if (DATE_ONLY_RE.test(iso)) return iso;
  return iso + 'Z';
}

export function parseServerTime(iso: string | null | undefined) {
  if (!iso) return null;
  return dayjs(ensureUtc(iso));
}

export function toServerUtc(d: Date | string | number | null | undefined): string | null {
  if (d === null || d === undefined || d === '') return null;
  return dayjs(d).utc().format('YYYY-MM-DDTHH:mm:ss');
}

export function formatDateTime(date: string | null | undefined): string {
  if (!date) return '-';
  return dayjs(ensureUtc(date)).format('YYYY-MM-DD HH:mm:ss');
}

export function formatDate(date: string | null | undefined): string {
  if (!date) return '-';
  return dayjs(ensureUtc(date)).format('YYYY-MM-DD');
}

export function formatPercent(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatStorageCapacity(gb: number): string {
  if (gb >= 1024) {
    return `${(gb / 1024).toFixed(1)} TB`;
  }
  return `${gb} GB`;
}

export function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN');
}

export function formatUPosition(uPosition: number | null, heightU: number): string {
  if (uPosition === null) return '-';
  return `U${uPosition}` + (heightU > 1 ? ` - U${uPosition + heightU - 1}` : '');
}

export function translateProbeError(error: string | null, t: DeviceT): string {
  if (!error) return '-';
  const code = Object.values(ProbeErrorCode).find((c) => c === error);
  if (code) return getProbeErrorMeta(code, t)?.label ?? error;
  const lower = error.toLowerCase().trim();
  for (const [key] of Object.entries(PROBE_ERROR_MAP)) {
    if (lower.includes(key)) return getProbeErrorMeta(key, t)?.label ?? error;
  }
  return error;
}

/**
 * 相对时间格式化（统一版，供监控总览页 / 告警页共用）。
 * P1 修复：原在 Overview 和 Alerts 两个文件重复定义且逻辑有差异，抽到 utils/format.ts 统一。
 */
export function relativeTime(iso: string | null, t: TFunction<'common'>): string {
  if (!iso) return '-';
  const utcIso = ensureUtc(iso);
  const diff = Date.now() - new Date(utcIso).getTime();
  if (diff < 60_000) return t('time.justNow');
  if (diff < 3_600_000) return t('time.minutesAgo', { count: Math.floor(diff / 60_000) });
  if (diff < 86_400_000) return t('time.hoursAgo', { count: Math.floor(diff / 3_600_000) });
  return t('time.daysAgo', { count: Math.floor(diff / 86_400_000) });
}
