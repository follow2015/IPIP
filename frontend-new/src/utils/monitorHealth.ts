import type { MonitorOverviewData } from '@/services/monitor';

export function calcHealthScore(overview: MonitorOverviewData): number {
  const total = overview.total_monitored || 0;
  if (total === 0) return 100;
  const reachable = overview.reachable || 0;
  const alerting = overview.alerting_devices || 0;
  const interrupted = overview.interrupted_devices || 0;
  const availability = reachable / total;
  const alertRatio = alerting / total;
  const interruptRatio = interrupted / total;
  const score = availability * 60 + (1 - alertRatio) * 30 + (1 - interruptRatio) * 10;
  return Math.round(Math.max(0, Math.min(100, score)));
}
