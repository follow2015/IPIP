import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, del, patch, put } from './api-client';
import apiClient from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { ApiResponse, PaginatedData, PaginationParams } from '@/types/api';
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
    refetchInterval: 30_000
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

export type MonitorCredentialListItem = components['schemas']['MonitorCredentialListItem'];

export interface LinkedDevice {
  device_id: number;
  device_name: string;
  device_type: string;
  management_ip: string | null;
}

export function useMonitorCredentials() {
  return useQuery({
    queryKey: queryKeys.monitor.credentials(),
    queryFn: async () => {
      const res = await get<MonitorCredentialListItem[]>('/monitor/credentials');
      return res.data ?? [];
    }
  });
}

export function useLinkedDevices(credentialId: number | null) {
  return useQuery({
    queryKey: queryKeys.monitor.linkedDevices(credentialId ?? 0),
    queryFn: async () => {
      const res = await get<LinkedDevice[]>(`/monitor/credentials/${credentialId}/devices`);
      return res.data ?? [];
    },
    enabled: credentialId != null && credentialId > 0
  });
}

export function usePatchCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { credentialId: number; enabled?: boolean; name?: string }) => {
      const res = await patch(`/monitor/credentials/${input.credentialId}`, {
        enabled: input.enabled,
        name: input.name
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useDeleteCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (credentialId: number) => {
      const res = await del(`/monitor/credentials/${credentialId}`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchDeleteCredentials() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await post('/monitor/credentials/batch-delete', { ids });
      return res.data as { deleted: number; failed: { id: number; reason: string }[] };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useCreateAndLinkCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      protocol: string;
      payload: Record<string, unknown>;
      name?: string;
      device_ids: number[];
    }) => {
      const res = await post('/monitor/credentials', input);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useLinkExistingCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { credentialId: number; device_ids: number[] }) => {
      const res = await post(`/monitor/credentials/${input.credentialId}/link`, {
        device_ids: input.device_ids
      });
      return res.data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      vars.device_ids.forEach((id) =>
        qc.invalidateQueries({ queryKey: queryKeys.monitor.status(id) })
      );
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUnlinkCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { deviceId: number; protocol: string }) => {
      const res = await del(`/monitor/devices/${input.deviceId}/credentials/${input.protocol}`);
      return res.data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(vars.deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUpdateSharedCredentialPayload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      credentialId: number;
      payload: Record<string, unknown>;
      name?: string;
    }) => {
      const res = await put<components['schemas']['MonitorCredentialPayloadUpdateResponse']>(
        `/monitor/credentials/${input.credentialId}/payload`,
        {
          payload: input.payload,
          name: input.name
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUpdateCredentialPayload(deviceId: number, credentialId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { payload: Record<string, unknown>; name?: string }) => {
      const res = await put<components['schemas']['MonitorCredentialPayloadUpdateResponse']>(
        `/monitor/devices/${deviceId}/credentials/${credentialId}/payload`,
        {
          payload: input.payload,
          name: input.name
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export type MonitorAlertItem = Required<components['schemas']['MonitorAlertListItem']>;

export type MonitorAlertDetail = Required<components['schemas']['MonitorAlertDetail']>;

export type DeviceMetricLatestItem = Required<components['schemas']['DeviceMetricLatestItem']>;

export interface MonitorAlertListData {
  items: MonitorAlertItem[];
  total: number;
  page: number;
  per_page: number;
}

export interface MonitorAlertQuery {
  alert_type?: string;
  severity?: string;
  status?: string;
  device_id?: number | null;
  start_date?: string;
  end_date?: string;
  metric_key?: string;
  index_key?: string;
  scope?: 'all' | 'mine';
  page?: number;
  per_page?: number;
}

export function useMonitorAlerts(params: MonitorAlertQuery) {
  return useQuery({
    queryKey: queryKeys.monitor.alerts(params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params.alert_type) qs.set('alert_type', params.alert_type);
      if (params.severity) qs.set('severity', params.severity);
      if (params.status) qs.set('status', params.status);
      if (params.device_id != null) qs.set('device_id', String(params.device_id));
      if (params.start_date) qs.set('start_date', params.start_date);
      if (params.end_date) qs.set('end_date', params.end_date);
      if (params.scope) qs.set('scope', params.scope);
      if (params.metric_key) qs.set('metric_key', params.metric_key);
      if (params.index_key) qs.set('index_key', params.index_key);
      if (params.page) qs.set('page', String(params.page));
      if (params.per_page) qs.set('per_page', String(params.per_page));
      const res = await get<MonitorAlertListData>(`/monitor/alerts?${qs.toString()}`);
      return res.data;
    }
  });
}

export function useAlertDetail(alertId: number | null) {
  return useQuery({
    queryKey: queryKeys.monitor.alertDetail(alertId ?? -1),
    queryFn: async () => {
      const res = await get<MonitorAlertDetail>(`/monitor/alerts/${alertId}`);
      return res.data;
    },
    enabled: alertId != null
  });
}

export function useRetryAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (alertId: number) => {
      const res = await post<{ retried: boolean; alert_id: number; status: string }>(
        `/monitor/alerts/${alertId}/retry`
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

export function useAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { alertId: number; note?: string }) => {
      const res = await post<{
        id: number;
        acknowledged_by: string;
        acknowledged_at: string | null;
        ack_note: string | null;
      }>(`/monitor/alerts/${input.alertId}/ack`, { note: input.note });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

export function useBatchAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { alertIds: number[]; note?: string }) => {
      const res = await post<{ acknowledged: number; not_found: number }>(
        '/monitor/alerts/batch-ack',
        { alert_ids: input.alertIds, note: input.note }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

export function useBatchRetryAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (alertIds: number[]) => {
      const res = await post<{ retried: number; skipped: number }>('/monitor/alerts/batch-retry', {
        alert_ids: alertIds
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

export interface MonitorAlertAggregationItem {
  alert_type: string;
  severity: string;
  device_id: number | null;
  device_name: string | null;
  count: number;
  first_at: string | null;
  last_at: string | null;
  window_minutes: number;
  sample_ids: number[];
  root_device_id: number | null;
}

export interface MonitorAlertAggregationQuery {
  window_minutes?: number;
  severity?: string;
  start_date?: string;
  end_date?: string;
  only_active?: boolean;
  max_groups?: number;
}

export function useAlertAggregations(params: MonitorAlertAggregationQuery) {
  return useQuery({
    queryKey: queryKeys.monitor.alertAggregations(params),
    queryFn: async () => {
      const search = new URLSearchParams();
      if (params.window_minutes) search.set('window_minutes', String(params.window_minutes));
      if (params.severity) search.set('severity', params.severity);
      if (params.start_date) search.set('start_date', params.start_date);
      if (params.end_date) search.set('end_date', params.end_date);
      if (params.only_active !== undefined)
        search.set('only_active', params.only_active ? '1' : '0');
      if (params.max_groups) search.set('max_groups', String(params.max_groups));
      const res = await get<MonitorAlertAggregationItem[]>(
        `/monitor/alerts/aggregations?${search.toString()}`
      );
      return res.data;
    }
  });
}

export type MonitorAlertStatistics = components['schemas']['MonitorAlertStatisticsResponse'];

export interface MonitorAlertStatisticsQuery {
  start_date?: string;
  end_date?: string;
  device_id?: number;
  severity?: string;
  bucket?: 'hour' | 'day';
  top_n?: number;
}

export function useAlertStatistics(params: MonitorAlertStatisticsQuery) {
  return useQuery({
    queryKey: queryKeys.monitor.alertStatistics(params),
    queryFn: async () => {
      const search = new URLSearchParams();
      if (params.start_date) search.set('start_date', params.start_date);
      if (params.end_date) search.set('end_date', params.end_date);
      if (params.device_id) search.set('device_id', String(params.device_id));
      if (params.severity) search.set('severity', params.severity);
      if (params.bucket) search.set('bucket', params.bucket);
      if (params.top_n) search.set('top_n', String(params.top_n));
      const res = await get<MonitorAlertStatistics>(
        `/monitor/alerts/statistics?${search.toString()}`
      );
      return res.data;
    }
  });
}

export function useCloseAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { alertId: number; reason?: string }) => {
      const res = await post<{
        id: number;
        closed_by: string;
        closed_at: string | null;
        close_reason: string | null;
      }>(`/monitor/alerts/${input.alertId}/close`, { reason: input.reason });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

export function useBatchCloseAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { alertIds: number[]; reason?: string }) => {
      const res = await post<{ closed: number; not_found: number }>('/monitor/alerts/batch-close', {
        alert_ids: input.alertIds,
        reason: input.reason
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
    }
  });
}

function _downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function useExportAlerts() {
  return useMutation({
    mutationFn: async (params: MonitorAlertQuery) => {
      const qs = new URLSearchParams();
      if (params.alert_type) qs.set('alert_type', params.alert_type);
      if (params.severity) qs.set('severity', params.severity);
      if (params.status) qs.set('status', params.status);
      if (params.device_id != null) qs.set('device_id', String(params.device_id));
      if (params.start_date) qs.set('start_date', params.start_date);
      if (params.end_date) qs.set('end_date', params.end_date);
      const res = await apiClient.get<Blob>(`/monitor/alerts/export?${qs.toString()}`, {
        responseType: 'blob'
      });
      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      _downloadBlob(res.data, `alerts_${today}.csv`);
    }
  });
}

export function useExportHistory() {
  return useMutation({
    mutationFn: async (input: { deviceId: number; start_date?: string; end_date?: string }) => {
      const qs = new URLSearchParams();
      if (input.start_date) qs.set('start_date', input.start_date);
      if (input.end_date) qs.set('end_date', input.end_date);
      const res = await apiClient.get<Blob>(
        `/monitor/devices/${input.deviceId}/history/export?${qs.toString()}`,
        { responseType: 'blob' }
      );
      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      _downloadBlob(res.data, `device_${input.deviceId}_history_${today}.csv`);
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

export interface DeviceMetricHistoryItem {
  id: number;
  device_id: number;
  metric_key: string;
  index_key: string;
  value: string | null;
  severity: string | null;
  breached: boolean;
  collected_at: string;
}

export interface DeviceMetricHistoryData {
  items: DeviceMetricHistoryItem[];
  total: number;
  from: string | null;
  to: string | null;
  index_key: string | null;
}

export interface DeviceMetricHistoryQuery {
  from?: string;
  to?: string;
  index_key?: string;
  limit?: number;
}

export function useDeviceMetricKeys(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.monitor.metricKeys(deviceId),
    queryFn: async () => {
      const res = await get<{ items: string[] }>(`/monitor/devices/${deviceId}/metric-keys`);
      return res.data;
    },
    enabled: deviceId > 0
  });
}

export function useDeviceMetricLatest(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.monitor.metricLatest(deviceId),
    queryFn: async () => {
      const res = await get<{ items: DeviceMetricLatestItem[] }>(
        `/monitor/devices/${deviceId}/metric-latest`
      );
      return res.data;
    },
    enabled: deviceId > 0
  });
}

export function useDeviceMetricHistory(
  deviceId: number,
  metricKey: string | undefined,
  params?: DeviceMetricHistoryQuery
) {
  return useQuery({
    queryKey: queryKeys.monitor.metricHistory(deviceId, metricKey ?? '', params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params?.from) qs.set('from', params.from);
      if (params?.to) qs.set('to', params.to);
      if (params?.index_key) qs.set('index_key', params.index_key);
      if (params?.limit != null) qs.set('limit', String(params.limit));
      const res = await get<DeviceMetricHistoryData>(
        `/monitor/devices/${deviceId}/metrics/${metricKey}/history?${qs.toString()}`
      );
      return res.data;
    },
    enabled: deviceId > 0 && !!metricKey
  });
}

export type DeviceTrafficPorts = components['schemas']['DeviceTrafficPortsResponse'];

export function useDeviceTrafficPorts(deviceId: number) {
  return useQuery({
    queryKey: ['monitor', 'traffic-ports', deviceId] as const,
    queryFn: async () => {
      const res = await get<DeviceTrafficPorts>(`/monitor/devices/${deviceId}/traffic/ports`);
      return res.data;
    },
    enabled: deviceId > 0,
    staleTime: 60 * 1000
  });
}

export function useDeviceTraffic(
  deviceId: number,
  port: string | undefined,
  from: number,
  till: number,
  enabled: boolean
) {
  return useQuery({
    queryKey: queryKeys.monitor.traffic(deviceId, port ?? '', from, till),
    queryFn: async () => {
      const res = await get<DeviceTraffic>(
        `/monitor/devices/${deviceId}/traffic?port=${encodeURIComponent(port!)}&from=${from}&till=${till}`
      );
      return res.data;
    },
    enabled: enabled && deviceId > 0 && !!port
  });
}

const metricTemplateHooks = createCrudHooks<
  MetricTemplateItem,
  MetricTemplateUpsert,
  MetricTemplateUpsert & { id: number }
>({
  basePath: '/monitor/metric-templates',
  queryKey: queryKeys.monitor.metricTemplatesCrud
});

export const useMetricTemplates = metricTemplateHooks.useList;

export function useUpsertMetricTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: MetricTemplateUpsert) => {
      const res = await put<{ id: number }>(`/monitor/metric-templates`, payload);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}

export type DeviceTraffic = components['schemas']['DeviceTrafficResponse'];

export type MetricTemplateList = components['schemas']['MetricTemplateListResponse'];

export type MetricTemplateItem = components['schemas']['MetricTemplateItem'];

export interface MetricTemplateUpsert {
  device_type: string;
  metric_key: string;
  category?: string | null;
  display_name?: string | null;
  source?: string;
  vendor?: string | null;
  mib?: string | null;
  oid_symbol?: string | null;
  oid?: string | null;
  zabbix_item_key?: string | null;
  index_kind?: string | null;
  metric_type?: string;
  unit?: string | null;
  poll_interval?: number;
  threshold?: Record<string, unknown> | null;
  severity_default?: string | null;
  enabled?: boolean;
  description?: string | null;
  runbook_url?: string | null;
  runbook_title?: string | null;
}

export interface MetricTemplateGroupItem {
  id: number;
  name: string;
  device_type: string;
  source: string;
  vendor: string | null;
  display_order: number;
  enabled: boolean;
  description: string | null;
  template_count?: number;
}

export interface MetricTemplateGroupDetail extends MetricTemplateGroupItem {
  templates: MetricTemplateItem[];
}

export interface MetricTemplateGroupUpsert {
  name: string;
  device_type: string;
  source: string;
  vendor?: string | null;
  display_order?: number;
  enabled?: boolean;
  description?: string | null;
}

export function useMetricTemplateGroups() {
  return useQuery({
    queryKey: queryKeys.monitor.metricTemplateGroups,
    queryFn: async () => {
      const res = await get<MetricTemplateGroupItem[]>('/monitor/metric-template-groups');
      return res.data;
    }
  });
}

export function useMetricTemplateGroupDetail(groupId: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.monitor.metricTemplateGroup(groupId),
    queryFn: async () => {
      const res = await get<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}`
      );
      return res.data;
    },
    enabled: enabled && groupId > 0
  });
}

export function useCreateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: MetricTemplateGroupUpsert) => {
      const res = await post<MetricTemplateGroupItem>('/monitor/metric-template-groups', payload);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups })
  });
}

export function useUpdateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number } & Partial<MetricTemplateGroupUpsert>) => {
      const res = await put<MetricTemplateGroupItem>(
        `/monitor/metric-template-groups/${id}`,
        payload
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useDeleteMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await del<{ id: number }>(`/monitor/metric-template-groups/${id}`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useAddTemplatesToGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, templateIds }: { groupId: number; templateIds: number[] }) => {
      const res = await post<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}/items`,
        { template_ids: templateIds }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useRemoveTemplateFromGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, templateId }: { groupId: number; templateId: number }) => {
      const res = await del<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}/items/${templateId}`
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchUpdateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      deviceIds,
      metricTemplateGroupId
    }: {
      deviceIds: number[];
      metricTemplateGroupId: number | null;
    }) => {
      const res = await post<{ updated: number; skipped: number }>(
        '/devices/batch-metric-template-group',
        { device_ids: deviceIds, metric_template_group_id: metricTemplateGroupId }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchUpdatePortSyncEnabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      deviceIds,
      portSyncEnabled
    }: {
      deviceIds: number[];
      portSyncEnabled: boolean | null;
    }) => {
      const res = await post<{
        updated: number;
        with_credential: number;
        without_credential: number;
        non_network: number;
        skipped: number;
      }>('/devices/batch-port-sync-enabled', {
        device_ids: deviceIds,
        port_sync_enabled: portSyncEnabled
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] });
    }
  });
}

export type DeviceMetricAlertItem = Required<components['schemas']['DeviceMetricAlertStateItem']>;
export interface DeviceMetricAlertListData {
  items: DeviceMetricAlertItem[];
}

export function useDeviceMetricAlerts(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.monitor.metricAlerts(deviceId),
    queryFn: async () => {
      const res = await get<DeviceMetricAlertListData>(
        `/monitor/devices/${deviceId}/metric-alerts`
      );
      return res.data;
    },
    enabled: deviceId > 0,
    refetchInterval: 30_000
  });
}

export interface DeviceMetricDashboardItem {
  metric_key: string;
  metric_name: string;
  source: string | null;
  value: string | null;
  severity: string | null;
  breached: boolean;
  collected_at: string | null;
}

export interface DeviceMetricDashboardData {
  device_id: number;
  has_credential: boolean;
  has_zabbix: boolean;
  configured_protocols: string[];
  template_group: {
    id: number;
    name: string;
    vendor?: string | null;
    templates?: DeviceMetricDashboardItem[];
  } | null;
  grouped: boolean;
  metric_status: DeviceMetricDashboardItem[];
  overall_status:
    | 'no_credential'
    | 'not_probed'
    | 'unreachable'
    | 'credential_error'
    | 'no_data'
    | 'breached'
    | 'normal';
  status_reason: string | null;
  reachable: boolean | null;
  last_error: string | null;
  last_checked_at: string | null;
}

export function useDeviceMetricDashboard(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.monitor.metricDashboard(deviceId),
    queryFn: async () => {
      const res = await get<DeviceMetricDashboardData>(
        `/monitor/devices/${deviceId}/metric-dashboard`
      );
      return res.data;
    },
    enabled: deviceId > 0,
    refetchInterval: 30_000
  });
}

export const useDeleteMetricTemplate = metricTemplateHooks.useDelete;

export function useBatchDeleteMetricTemplates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await del<{ deleted: number; total: number }>('/monitor/metric-templates/batch', {
        ids
      });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}

export function useBatchToggleMetricTemplateEnabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { ids: number[]; enabled: boolean }) => {
      const res = await patch<{ updated: number; total: number; enabled: boolean }>(
        '/monitor/metric-templates/batch-enabled',
        params
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}

export type MonitorSilenceRule = Required<components['schemas']['MonitorSilenceRuleItem']>;

export interface MonitorSilenceRuleInput {
  name: string;
  device_ids?: number[] | null;
  alert_types?: string[] | null;
  silence_from: string;
  silence_until: string;
  reason?: string;
  enabled?: boolean;
}

const silenceRuleHooks = createCrudHooks<
  MonitorSilenceRule,
  MonitorSilenceRuleInput,
  Partial<MonitorSilenceRuleInput> & { id: number }
>({
  basePath: '/monitor/silence-rules',
  queryKey: queryKeys.monitor.silenceRulesCrud
});

export const useSilenceRules = silenceRuleHooks.useList;
export const useCreateSilenceRule = silenceRuleHooks.useCreate;
export const useUpdateSilenceRule = silenceRuleHooks.useUpdate;
export const useDeleteSilenceRule = silenceRuleHooks.useDelete;

export type MonitorAlertDependencyRule = Required<
  components['schemas']['MonitorAlertDependencyRuleItem']
>;

export interface MonitorAlertDependencyRuleInput {
  name: string;
  upstream_device_id: number;
  downstream_device_id: number;
  alert_types?: string[] | null;
  reason?: string;
  enabled?: boolean;
}

const alertDependencyRuleHooks = createCrudHooks<
  MonitorAlertDependencyRule,
  MonitorAlertDependencyRuleInput,
  Partial<MonitorAlertDependencyRuleInput> & { id: number }
>({
  basePath: '/monitor/alert-dependency-rules',
  queryKey: queryKeys.monitor.alertDependencyRulesCrud
});

export const useAlertDependencyRules = alertDependencyRuleHooks.useList;
export const useCreateAlertDependencyRule = alertDependencyRuleHooks.useCreate;
export const useUpdateAlertDependencyRule = alertDependencyRuleHooks.useUpdate;
export const useDeleteAlertDependencyRule = alertDependencyRuleHooks.useDelete;

export type MonitorSlaTarget = Required<components['schemas']['MonitorSlaTargetItem']>;
export type MonitorSlaAchievement = components['schemas']['MonitorSlaAchievement'];

export interface MonitorSlaTargetInput {
  name: string;
  target_device_ids: number[];
  target_ratio: number;
  window_days?: number;
  description?: string;
  enabled?: boolean;
}

const slaTargetHooks = createCrudHooks<
  MonitorSlaTarget,
  MonitorSlaTargetInput,
  Partial<MonitorSlaTargetInput> & { id: number }
>({
  basePath: '/monitor/sla-targets',
  queryKey: queryKeys.monitor.slaTargetsCrud
});

export const useSlaTargets = slaTargetHooks.useList;
export const useCreateSlaTarget = slaTargetHooks.useCreate;
export const useUpdateSlaTarget = slaTargetHooks.useUpdate;
export const useDeleteSlaTarget = slaTargetHooks.useDelete;

export function useSlaAchievements(start?: string, end?: string) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const qs = params.toString() ? `?${params.toString()}` : '';
  return useQuery({
    queryKey: [...queryKeys.monitor.slaAchievements, start, end],
    queryFn: async () => {
      const res = await get<PaginatedData<MonitorSlaAchievement>>(
        `/monitor/sla-targets/achievements${qs}`
      );
      return res.data;
    }
  });
}

export type DeviceMetricOverride = Required<components['schemas']['DeviceMetricOverrideItem']>;

export interface DeviceMetricOverrideInput {
  device_id: number;
  metric_key: string;
  threshold: Record<string, unknown>;
  enabled?: boolean;
  note?: string;
}

export interface ThresholdOverrideQueryParams extends PaginationParams {
  device_id?: number;
  metric_key?: string;
}

const thresholdOverrideHooks = createCrudHooks<
  DeviceMetricOverride,
  DeviceMetricOverrideInput,
  DeviceMetricOverrideInput & { id: number },
  ThresholdOverrideQueryParams
>({
  basePath: '/monitor/threshold-overrides',
  queryKey: queryKeys.monitor.thresholdOverridesCrud
});

export const useThresholdOverrides = thresholdOverrideHooks.useList;

export function useUpsertThresholdOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: DeviceMetricOverrideInput) => {
      const res = await post<DeviceMetricOverride>('/monitor/threshold-overrides', input);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.thresholdOverridesCrud })
  });
}

export const useDeleteThresholdOverride = thresholdOverrideHooks.useDelete;

export type MonitorEscalationPolicy = Required<
  components['schemas']['MonitorEscalationPolicyItem']
>;

export interface MonitorEscalationStepInput {
  step_no?: number;
  wait_minutes: number;
  escalate_severity?: string | null;
  escalate_to_role_id?: number | null;
  escalate_webhook_url?: string | null;
  enabled?: boolean;
}

export interface MonitorEscalationPolicyInput {
  name: string;
  alert_type?: string | null;
  severity?: string | null;
  wait_minutes: number;
  escalate_severity?: string | null;
  escalate_to_role_id?: number | null;
  escalate_webhook_url?: string | null;
  repeat_minutes?: number;
  enabled?: boolean;
  steps?: MonitorEscalationStepInput[] | null;
}

const escalationPolicyHooks = createCrudHooks<
  MonitorEscalationPolicy,
  MonitorEscalationPolicyInput,
  Partial<MonitorEscalationPolicyInput> & { id: number }
>({
  basePath: '/monitor/escalation-policies',
  queryKey: queryKeys.monitor.escalationPoliciesCrud
});

export const useEscalationPolicies = escalationPolicyHooks.useList;
export const useCreateEscalationPolicy = escalationPolicyHooks.useCreate;
export const useUpdateEscalationPolicy = escalationPolicyHooks.useUpdate;
export const useDeleteEscalationPolicy = escalationPolicyHooks.useDelete;

export interface MibScanResult {
  device_ip: string;
  vendor_id?: string | null;
  oid_count: number;
  type_summary: Record<string, number>;
  detected: MibScanOid[];
  hint: string;
}

export interface MibScanOid {
  oid: string;
  type: string;
  value: string;
  category?: string | null;
  category_label?: string | null;
  category_source?: 'rule' | 'heuristic' | null;
}

export interface MibImportItem {
  oid: string;
  metric_key: string;
  device_type: string;
  category?: string | null;
  display_name?: string | null;
  vendor?: string | null;
  oid_symbol?: string | null;
  metric_type?: string;
  unit?: string;
  severity_default?: string | null;
  description?: string;
}

export function useMibScan() {
  return useMutation({
    mutationFn: async (params: { device_id: number; timeout?: number }) => {
      const res = await apiClient.post<ApiResponse<MibScanResult>>(
        '/monitor/mib-scan',
        params as unknown as Record<string, unknown>,
        { timeout: 120_000 }
      );
      return res.data.data;
    }
  });
}

export function useImportOids() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (items: MibImportItem[]) => {
      const res = await post<{
        imported: { id: number; metric_key: string; oid: string }[];
        count: number;
      }>('/monitor/mib-scan/import', { items });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}


export type OidCategoryRule = Required<components['schemas']['OidCategoryRuleItem']>;

export type DeviceTypeRecommend = Required<components['schemas']['DeviceTypeRecommendItem']>;

const oidCategoryRuleHooks = createCrudHooks<
  OidCategoryRule,
  Omit<OidCategoryRule, 'id'>,
  Partial<OidCategoryRule> & { id: number }
>({
  basePath: '/monitor/oid-category-rules',
  queryKey: queryKeys.monitor.oidCategoryRulesCrud
});

export const useOidCategoryRules = oidCategoryRuleHooks.useList;
export const useCreateOidCategoryRule = oidCategoryRuleHooks.useCreate;
export const useUpdateOidCategoryRule = oidCategoryRuleHooks.useUpdate;
export const useDeleteOidCategoryRule = oidCategoryRuleHooks.useDelete;

export function useDeviceTypeRecommends() {
  return useQuery({
    queryKey: queryKeys.monitor.deviceTypeRecommends,
    queryFn: async () => {
      const res = await get<{ total: number; items: DeviceTypeRecommend[] }>(
        '/monitor/device-type-recommends'
      );
      return res.data;
    }
  });
}

export function useUpdateDeviceTypeRecommend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      device_type,
      categories
    }: {
      device_type: string;
      categories: string[];
    }) => {
      const res = await put<{ device_type: string; categories: string[] }>(
        `/monitor/device-type-recommends/${device_type}`,
        { categories }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.deviceTypeRecommends })
  });
}

export function useRecommendConfig(deviceType: string) {
  return useQuery({
    queryKey: queryKeys.monitor.recommendConfig(deviceType),
    queryFn: async () => {
      const res = await get<{ device_type: string; categories: string[] }>(
        `/monitor/mib-scan/recommend-config?device_type=${deviceType}`
      );
      return res.data.categories;
    }
  });
}

export function usePersistHeuristicRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { oid: string; device_type: string; vendor_id?: string | null }) => {
      const res = await post<{ id: number }>('/monitor/mib-scan/persist-rule', params);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.oidCategoryRulesCrud })
  });
}

export type VendorBrand = Required<components['schemas']['VendorBrandItem']>;

export interface VendorBrandQueryParams extends PaginationParams {
  device_type?: string;
}

const vendorBrandHooks = createCrudHooks<
  VendorBrand,
  Omit<VendorBrand, 'id'>,
  Partial<VendorBrand> & { id: number },
  VendorBrandQueryParams
>({
  basePath: '/monitor/vendor-brands',
  queryKey: queryKeys.monitor.vendorBrandsCrud
});

export const useVendorBrands = vendorBrandHooks.useList;

export function useCreateVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (brand: Omit<VendorBrand, 'id'>) => {
      const res = await post<{ id: number }>('/monitor/vendor-brands', brand);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}

export function useUpdateVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...rest }: Partial<VendorBrand> & { id: number }) => {
      const res = await patch<{ id: number }>(
        `/monitor/vendor-brands/${id}`,
        rest as Record<string, unknown>
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}

export function useDeleteVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await del<{ id: number }>(`/monitor/vendor-brands/${id}`);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}
