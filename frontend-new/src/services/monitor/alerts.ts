
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { get, post } from '../api-client';
import { queryKeys } from '../query-keys';
import { useAuthStore } from '@/stores/auth';

import type { components } from '@/types/api-generated';

export type MonitorAlertItem = Required<components['schemas']['MonitorAlertListItem']>;

export type MonitorAlertDetail = Required<components['schemas']['MonitorAlertDetail']>;

export interface MonitorAlertPort {
  index: string | null;
  name: string | null;
  alias: string | null;
  oper_status: string | null;
  shutdown: boolean | null;
  source: 'payload' | 'varbinds';
}

export function asAlertPort(port: MonitorAlertDetail['port']): MonitorAlertPort | null {
  if (!port || typeof port !== 'object') return null;
  const p = port as Record<string, unknown>;
  return {
    index: typeof p.index === 'string' ? p.index : null,
    name: typeof p.name === 'string' ? p.name : null,
    alias: typeof p.alias === 'string' ? p.alias : null,
    oper_status: typeof p.oper_status === 'string' ? p.oper_status : null,
    shutdown: typeof p.shutdown === 'boolean' ? p.shutdown : null,
    source: p.source === 'varbinds' ? 'varbinds' : 'payload'
  };
}

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

export function optimisticPatchAlert(
  qc: QueryClient,
  alertId: number,
  patch: (alert: MonitorAlertItem) => MonitorAlertItem
): () => void {
  const filters = { queryKey: queryKeys.monitor.alertsAll };
  const snapshot = qc.getQueriesData<MonitorAlertListData>(filters);
  qc.setQueriesData<MonitorAlertListData>(filters, (old) => {
    if (!old || !Array.isArray(old.items)) return old;
    return {
      ...old,
      items: old.items.map((a) => (a.id === alertId ? patch(a) : a))
    };
  });
  return () => {
    for (const [key, data] of snapshot) {
      qc.setQueryData(key, data);
    }
  };
}

const OPTIMISTIC_ACTOR_FALLBACK = 'me';
export function currentUsername(): string {
  return useAuthStore.getState().user?.username || OPTIMISTIC_ACTOR_FALLBACK;
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
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: queryKeys.monitor.alertsAll });
      const rollback = optimisticPatchAlert(qc, input.alertId, (a) => ({
        ...a,
        acknowledged_by: a.acknowledged_by || currentUsername(),
        acknowledged_at: a.acknowledged_at || new Date().toISOString(),
        ack_note: input.note ?? a.ack_note
      }));
      return { rollback };
    },
    onError: (_err, _input, ctx) => {
      ctx?.rollback();
    },
    onSettled: () => {
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
