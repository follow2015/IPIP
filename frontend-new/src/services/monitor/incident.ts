
import { useQuery } from '@tanstack/react-query';
import { get } from '../api-client';
import { queryKeys } from '../query-keys';

import type { PaginatedData } from '@/types/api';


export interface IncidentItem {
  id: number;
  incident_key: string;
  title: string;
  severity: string;
  status: string;
  reason_code: string | null;
  root_device_id: number | null;
  root_device_name: string | null;
  alert_count: number;
  device_count: number;
  first_alert_at: string | null;
  last_alert_at: string | null;
  closed_at: string | null;
}

export interface IncidentRelatedAlert {
  id: number;
  device_id: number | null;
  alert_type: string;
  severity: string;
  dedup_key: string;
  status: string;
  attempts: number;
  last_error: string | null;
  next_retry_at: string | null;
  created_at: string | null;
  sent_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  ack_note: string | null;
  closed_by: string | null;
  closed_at: string | null;
  close_reason: string | null;
  incident_id: number | null;
  reason_code: string | null;
}

export interface IncidentSuppressedLog {
  id: number;
  device_id: number | null;
  device_name: string | null;
  alert_type: string;
  severity: string;
  reason_code: string;
  upstream_device_id: number | null;
  upstream_device_name: string | null;
  incident_id: number | null;
  created_at: string | null;
}

export interface IncidentDetail extends IncidentItem {
  related_alerts: IncidentRelatedAlert[];
  suppressed_logs: IncidentSuppressedLog[];
}

export interface IncidentListParams {
  status?: 'active' | 'acknowledged' | 'closed';
  device_name?: string;
  page?: number;
  per_page?: number;
}

export function useIncidents(params: IncidentListParams = {}) {
  return useQuery({
    queryKey: queryKeys.monitor.incidents(params),
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params.status) qs.set('status', params.status);
      if (params.device_name) qs.set('device_name', params.device_name);
      if (params.page) qs.set('page', String(params.page));
      if (params.per_page) qs.set('per_page', String(params.per_page));
      const res = await get<PaginatedData<IncidentItem>>(`/monitor/incidents?${qs.toString()}`);
      return res.data;
    },
    refetchInterval: 30_000,
    refetchIntervalInBackground: true
  });
}

export function useIncidentDetail(incidentId: number | null) {
  return useQuery({
    queryKey: queryKeys.monitor.incidentDetail(incidentId ?? -1),
    queryFn: async () => {
      const res = await get<IncidentDetail>(`/monitor/incidents/${incidentId}`);
      return res.data;
    },
    enabled: incidentId != null
  });
}
