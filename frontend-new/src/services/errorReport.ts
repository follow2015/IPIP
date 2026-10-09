import { post } from './api-client';
import { useAuthStore } from '@/stores/auth';

const DEDUPE_WINDOW_MS = 60_000;
const MAX_TRACKED = 200;

const lastReportedAt = new Map<string, number>();

function shouldReport(key: string): boolean {
  const now = Date.now();
  const last = lastReportedAt.get(key);
  if (last !== undefined && now - last < DEDUPE_WINDOW_MS) return false;
  if (lastReportedAt.size >= MAX_TRACKED) lastReportedAt.clear();
  lastReportedAt.set(key, now);
  return true;
}

export function resetErrorReportDedupe(): void {
  lastReportedAt.clear();
}

export function reportClientError(error: Error, context?: Record<string, unknown>): void {
  try {
    if (!useAuthStore.getState().token) return;

    const key = `${error.name}:${error.message}`;
    if (!shouldReport(key)) return;

    void post('/api/errors/report', {
      errors: [
        {
          name: error.name,
          message: error.message,
          stack: error.stack,
          url: typeof globalThis.location === 'undefined' ? undefined : globalThis.location.href,
          user_agent: typeof navigator === 'undefined' ? undefined : navigator.userAgent,
          ...context
        }
      ]
    }).catch(() => undefined); // 约束 2：上报失败静默
  } catch {
  }
}
