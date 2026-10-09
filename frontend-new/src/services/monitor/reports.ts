
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post } from '../api-client';
import apiClient from '../api-client';
import { queryKeys } from '../query-keys';

import type { components } from '@/types/api-generated';
import { currentUsername, optimisticPatchAlert } from './alerts';
import type { MonitorAlertQuery } from './alerts';

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
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: queryKeys.monitor.alertsAll });
      const rollback = optimisticPatchAlert(qc, input.alertId, (a) => ({
        ...a,
        closed_by: a.closed_by || currentUsername(),
        closed_at: a.closed_at || new Date().toISOString(),
        close_reason: input.reason ?? a.close_reason
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
