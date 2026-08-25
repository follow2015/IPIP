/**
 * 仪表盘服务
 * - 获取统计数据
 * - 获取活动记录
 * - 获取系统状态
 * - TanStack Query hooks
 */
import { useQuery, useSuspenseQuery } from '@tanstack/react-query';
import { get } from './api-client';
import type { DashboardStats, DashboardActivity, SystemStatus } from '@/types/models';


async function fetchDashboardStats() {
  return get<DashboardStats>('/dashboard/stats');
}


async function fetchActivities(limit = 20) {
  return get<{ activities: DashboardActivity[]; total: number }>(`/dashboard/activities?limit=${limit}`);
}


async function fetchSystemStatus() {
  return get<SystemStatus>('/dashboard/system-status');
}


export const DASHBOARD_KEYS = {
  stats: ['dashboard', 'stats'] as const,
  activities: (limit = 20) => ['dashboard', 'activities', limit] as const,
  systemStatus: ['dashboard', 'system-status'] as const,
};


export function useDashboardStats() {
  return useQuery({
    queryKey: DASHBOARD_KEYS.stats,
    queryFn: async () => {
      const res = await fetchDashboardStats();
      return res.data;
    },
  });
}


export function useDashboardSuspenseStats() {
  return useSuspenseQuery({
    queryKey: DASHBOARD_KEYS.stats,
    queryFn: async () => {
      const res = await fetchDashboardStats();
      return res.data;
    },
  });
}


export function useDashboardActivities(limit = 20) {
  return useQuery({
    queryKey: DASHBOARD_KEYS.activities(limit),
    queryFn: async () => {
      const res = await fetchActivities(limit);
      return res.data;
    },
    
    staleTime: 60_000,
  });
}


export function useSystemStatus() {
  return useQuery({
    queryKey: DASHBOARD_KEYS.systemStatus,
    queryFn: async () => {
      const res = await fetchSystemStatus();
      return res.data;
    },
    
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
}
