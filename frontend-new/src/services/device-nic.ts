/**
 * 设备网卡端口服务
 * - 子资源 CRUD + TanStack Query hooks
 * 对齐后端 /api/devices/<id>/ports 端点（device_nics_port 表）
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { unwrapNested } from './service-utils';
import { queryKeys } from './query-keys';
import type { DeviceNicPort, DevicePortsResponse } from '@/types/models';


interface NicPortRequest {
  nic_number: number;
  port_number: number;
  port_name?: string;
  port_type?: string;
  port_speed?: string;
  port_status?: string;
  description?: string;
}


interface BatchCreateNicRequest {
  ports: NicPortRequest[];
}


interface BatchDeleteNicRequest {
  port_ids: number[];
}


async function fetchDevicePorts(deviceId: number) {
  const res = await get<DevicePortsResponse>(`/devices/${deviceId}/nics`);
  return unwrapNested(res, 'ports');
}


export function useDeviceNics(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.devices.nics(deviceId),
    queryFn: async () => {
      const res = await fetchDevicePorts(deviceId);
      return res.data as DeviceNicPort[];
    },
    enabled: deviceId > 0
  });
}


export function useCreateNic(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NicPortRequest) =>
      post<{ ports: DeviceNicPort[] }>(`/devices/${deviceId}/nics/batch-create`, { ports: [data] }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.nics(deviceId) });
    }
  });
}


export function useUpdateNic(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ portId, data }: { portId: number; data: Partial<NicPortRequest> }) =>
      put<DeviceNicPort>(`/devices/${deviceId}/nics/${portId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.nics(deviceId) });
    }
  });
}


export function useDeleteNic(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (portId: number) => del<void>(`/devices/${deviceId}/nics/${portId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.nics(deviceId) });
    }
  });
}


export function useBatchCreateNics(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchCreateNicRequest) =>
      post<{ ports: DeviceNicPort[] }>(`/devices/${deviceId}/nics/batch-create`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.nics(deviceId) });
    }
  });
}


export function useBatchDeleteNics(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchDeleteNicRequest) =>
      del<{ deleted: number[]; skipped: { id: number; reason: string }[] }>(
        `/devices/${deviceId}/nics/batch`,
        data
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.nics(deviceId) });
    }
  });
}


export type { NicPortRequest, BatchCreateNicRequest, BatchDeleteNicRequest };
