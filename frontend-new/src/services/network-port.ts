/**
 * 统一端口服务（network_ports 表）
 * - 合并原 device-switch-port.ts
 * - 统一端口列表查询 + 手动 CRUD + 状态更新
 * 对齐后端 /api/devices/<id>/ports 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { unwrapNested } from './service-utils';
import { queryKeys } from './query-keys';
import type { SwitchPort } from '@/types/models';

async function fetchNetworkPorts(deviceId: number) {
  const res = await get<{ ports: SwitchPort[] }>(`/devices/${deviceId}/ports`);
  return unwrapNested(res, 'ports');
}

export function useNetworkPorts(deviceId: number, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.devices.networkPorts(deviceId),
    queryFn: async () => {
      const res = await fetchNetworkPorts(deviceId);
      return res.data as SwitchPort[];
    },
    enabled: options?.enabled ?? deviceId > 0
  });
}

interface CreatePortRequest {
  port_name: string;
  port_type?: string;
  speed?: string;
  usage_status?: string;
  description?: string;
}

export function useCreateNetworkPort(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreatePortRequest) => post<SwitchPort>(`/devices/${deviceId}/ports`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    }
  });
}

export function useBatchCreateNetworkPorts(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ports: CreatePortRequest[]) =>
      post<{ created_count: number }>('/devices/switch-ports/batch', {
        device_id: deviceId,
        ports
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    }
  });
}

interface UpdatePortRequest {
  port_name?: string;
  port_type?: string;
  speed?: string;
  usage_status?: string;
  description?: string;
  vlan?: string | null;
  mac?: string | null;
  ip_address?: string | null;
  raw_info?: string | null;
  customer_id?: number | null;
}

export function useUpdateNetworkPort(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ portId, data }: { portId: number; data: Partial<UpdatePortRequest> }) =>
      put<SwitchPort>(`/devices/switch-ports/${portId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    }
  });
}

export function useDeleteNetworkPort(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (portId: number) => del<void>(`/devices/switch-ports/${portId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    }
  });
}

export function useUpdatePortUsageStatus(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ portId, usageStatus }: { portId: number; usageStatus: string }) =>
      put<SwitchPort>(`/devices/switch-ports/${portId}`, { usage_status: usageStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    }
  });
}


export interface DevicePortSyncEnabled {
  port_sync_enabled: boolean | null;
  global_enabled: boolean;
  effective_enabled: boolean;
}

export function useDevicePortSyncEnabled(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.devices.portSyncEnabled(deviceId),
    queryFn: async () => {
      const res = await get<DevicePortSyncEnabled>(`/devices/${deviceId}/port-sync-enabled`);
      return res.data as DevicePortSyncEnabled;
    },
    enabled: deviceId > 0
  });
}

export function useSetDevicePortSyncEnabled(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: boolean | null) =>
      put<DevicePortSyncEnabled>(`/devices/${deviceId}/port-sync-enabled`, {
        port_sync_enabled: value
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.portSyncEnabled(deviceId) });
    }
  });
}
