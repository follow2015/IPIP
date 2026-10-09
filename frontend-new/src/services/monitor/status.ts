
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, patch, put } from '../api-client';
import { queryKeys } from '../query-keys';

import type { components } from '@/types/api-generated';

export interface DeviceMonitorStatusData {
  monitored: boolean;
  configured_protocols: string[];
  credentials?: { protocol: string; credential_id: number; name: string | null }[];
  status: {
    id: number;
    device_id: number;
    protocol: string;
    reachable: boolean;
    ever_reachable: boolean;
    down_alerted: boolean;
    down_episode: number;
    last_reachable_at: string | null;
    last_unreachable_at: string | null;
    last_checked_at: string;
    consecutive_failures: number;
    latency_ms: number | null;
    extra: Record<string, unknown> | null;
    last_error: string | null;
    monitor_enabled?: boolean;
  } | null;
  active_metric_alerts?: number;
  max_alert_severity?: number;
  monitor_interrupted?: boolean;
}

export function useDeviceMonitorStatus(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.monitor.status(deviceId),
    queryFn: async () => {
      const res = await get<DeviceMonitorStatusData>(`/monitor/devices/${deviceId}/status`);
      return res.data;
    },
    enabled: deviceId > 0,
    refetchInterval: 30_000 // 30s，对齐后台最短 60s 轮询；用户离开页面 TanStack Query 默认停止刷新
  });
}

export type MonitorRecentAlert = Required<components['schemas']['MonitorOverviewRecentAlert']>;
export type MonitorOverviewData = Required<
  Omit<components['schemas']['MonitorOverviewResponse'], 'recent_alerts'>
> & {
  recent_alerts: MonitorRecentAlert[];
};

export function useMonitorOverview() {
  return useQuery({
    queryKey: queryKeys.monitor.overview,
    queryFn: async () => {
      const res = await get<MonitorOverviewData>('/monitor/overview');
      return res.data;
    },
    refetchInterval: 30_000,
    refetchIntervalInBackground: true
  });
}

export type MonitorStatusItem = Required<components['schemas']['MonitorStatusListItem']>;

export interface MonitorStatusListData {
  items: MonitorStatusItem[];
  total: number;
  page: number;
  per_page: number;
}

export type MonitorStatusFilter =
  'unreachable' | 'flapping' | 'blindspot' | 'metric_alerting' | 'interrupted' | undefined;

export function useMonitorStatuses(params: {
  status_filter?: MonitorStatusFilter;
  page?: number;
  per_page?: number;
  keyword?: string;
}) {
  return useQuery({
    queryKey: queryKeys.monitor.statuses(params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params.status_filter) qs.set('status_filter', params.status_filter);
      if (params.page) qs.set('page', String(params.page));
      if (params.per_page) qs.set('per_page', String(params.per_page));
      if (params.keyword) qs.set('keyword', params.keyword);
      const res = await get<MonitorStatusListData>(`/monitor/statuses?${qs.toString()}`);
      return res.data;
    }
  });
}

export interface MonitorConfigItem {
  value: number | string | boolean;
  editable: boolean;
  type: 'int' | 'string' | 'bool' | 'float' | 'json';
  description: string;
}

export type MonitorConfigData = Record<string, MonitorConfigItem>;

export function useMonitorConfig() {
  return useQuery({
    queryKey: queryKeys.monitor.config,
    queryFn: async () => {
      const res = await get<MonitorConfigData>('/monitor/config');
      return res.data;
    },
    staleTime: Infinity
  });
}

export function useUpdateMonitorConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (updates: Record<string, number | string | boolean>) => {
      const res = await put<{ updated: string[]; requires_restart: string[] }>('/monitor/config', {
        updates
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.config });
    }
  });
}

export type ProbeResultData = Required<components['schemas']['MonitorProbeResultResponse']>;

export function useCheckDeviceNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (deviceId: number) => {
      const res = await post<ProbeResultData>(`/monitor/devices/${deviceId}/check`);
      return res.data;
    },
    onSuccess: (_data, deviceId) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.overview });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
    }
  });
}

export interface BatchProbeResultData {
  device_id: number;
  reachable: boolean | null;
  latency_ms: number | null;
  extra: Record<string, unknown> | null;
  error: string | null;
}

export interface CheckBatchResponse {
  results: BatchProbeResultData[];
  skipped: number[];
}

export function useCheckBatchDevices() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (deviceIds: number[]) => {
      const res = await post<CheckBatchResponse>('/monitor/check-batch', { device_ids: deviceIds });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.overview });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
    }
  });
}

export function useToggleDeviceMonitor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { deviceId: number; enabled: boolean }) => {
      const res = await patch<{ device_id: number; monitor_enabled: boolean }>(
        `/monitor/devices/${input.deviceId}/monitor-enabled`,
        { enabled: input.enabled }
      );
      return res.data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(vars.deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.overview });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
    }
  });
}

export interface BatchMonitorEnabledResult {
  updated: number;
  skipped: number;
}

export function useBatchToggleDeviceMonitor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { deviceIds: number[]; enabled: boolean }) => {
      const res = await patch<BatchMonitorEnabledResult>('/monitor/batch-monitor-enabled', {
        device_ids: input.deviceIds,
        enabled: input.enabled
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.overview });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
    }
  });
}

export interface ProbeHistoryItem {
  id: number;
  device_id: number;
  protocol: string;
  reachable: boolean;
  latency_ms: number | null;
  consecutive_failures: number;
  episode: number;
  is_alert: boolean;
  error: string | null;
  extra: Record<string, unknown> | null;
  loss_pct: number | null;
  jitter_ms: number | null;
  samples: number | null;
  probed_at: string;
  created_at: string;
}

export interface ProbeHistoryData {
  items: ProbeHistoryItem[];
  total: number;
  from: string | null;
  to: string | null;
  protocol: string | null;
}

export type ProbeTrends = Required<components['schemas']['MonitorProbeTrendsResponse']>;

export interface ProbeHistoryQuery {
  from?: string;
  to?: string;
  protocol?: string;
  limit?: number;
}

export function useProbeHistory(deviceId: number, params?: ProbeHistoryQuery) {
  return useQuery({
    queryKey: queryKeys.monitor.history(deviceId, params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params?.from) qs.set('from', params.from);
      if (params?.to) qs.set('to', params.to);
      if (params?.protocol) qs.set('protocol', params.protocol);
      if (params?.limit != null) qs.set('limit', String(params.limit));
      const res = await get<ProbeHistoryData>(
        `/monitor/devices/${deviceId}/history?${qs.toString()}`
      );
      return res.data;
    },
    enabled: deviceId > 0
  });
}

export function useProbeTrends(deviceId: number, params?: ProbeHistoryQuery) {
  return useQuery({
    queryKey: queryKeys.monitor.trends(deviceId, params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params?.from) qs.set('from', params.from);
      if (params?.to) qs.set('to', params.to);
      if (params?.protocol) qs.set('protocol', params.protocol);
      const res = await get<ProbeTrends>(`/monitor/devices/${deviceId}/trends?${qs.toString()}`);
      return res.data;
    },
    enabled: deviceId > 0
  });
}
