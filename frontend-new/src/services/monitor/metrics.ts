
import { useQuery } from '@tanstack/react-query';
import { get } from '../api-client';
import { queryKeys } from '../query-keys';

import type { components } from '@/types/api-generated';
import type { DeviceMetricLatestItem } from './alerts';

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

export type DeviceTraffic = components['schemas']['DeviceTrafficResponse'];

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

export type MonitorStatusCode =
  | 'no_credential'
  | 'not_probed'
  | 'credential_error'
  | 'unreachable'
  | 'normal'
  | 'normal_no_group'
  | 'no_data'
  | 'no_data_template'
  | 'breached';

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
  monitor_status_code?: MonitorStatusCode | null;
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

