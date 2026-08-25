/**
 * 格式化工具
 * - 日期/数字/容量格式化
 */
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import { PROBE_ERROR_MAP, ProbeErrorCode } from '@/types/enums';


dayjs.extend(utc);


export function ensureUtc(iso: string): string {
  
  
  if (iso.endsWith('Z') || iso.endsWith('+00:00')) return iso;
  return iso + 'Z';
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


export function translateProbeError(error: string | null): string {
  if (!error) return '-';
  
  const code = Object.values(ProbeErrorCode).find((c) => c === error);
  if (code) return PROBE_ERROR_MAP[code].label;
  
  const lower = error.toLowerCase().trim();
  for (const [key, entry] of Object.entries(PROBE_ERROR_MAP)) {
    if (lower.includes(key)) return entry.label;
  }
  return error;
}


export function relativeTime(iso: string | null): string {
  if (!iso) return '-';
  
  const utcIso = iso.endsWith('Z') || iso.endsWith('+00:00') ? iso : iso + 'Z';
  const diff = Date.now() - new Date(utcIso).getTime();
  
  if (diff < 0) return '刚刚';
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`;
  return `${Math.floor(diff / 86_400_000)}天前`;
}
