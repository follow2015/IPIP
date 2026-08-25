/**
 * 设备存储服务
 * - CRUD + 分组/详细视图 + TanStack Query hooks
 * 对齐后端 /api/devices/<id>/storage 和 /api/storage/<id> 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { unwrapNested } from './service-utils';
import { queryKeys } from './query-keys';
import type {
  DeviceStorageDetail,
  DeviceStorageGrouped,
  DeviceStorageResponse
} from '@/types/models';

interface StorageRequest {
  storage_type: string;
  capacity?: string;
  capacity_gb?: number;
  interface_type?: string;
  slot_number?: number;
  manufacturer?: string;
  model?: string;
  serial_number?: string;
  firmware?: string;
  status?: string;
  template_id?: number;
  count?: number;
}

async function fetchDeviceStorage(deviceId: number, grouped = true) {
  const res = await get<DeviceStorageResponse>(`/devices/${deviceId}/storage`, { grouped });
  return unwrapNested(res, 'storage');
}

export function useDeviceStorage(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.devices.storage(deviceId),
    queryFn: async () => {
      const res = await fetchDeviceStorage(deviceId, true);
      return res.data as DeviceStorageGrouped[];
    },
    enabled: deviceId > 0
  });
}

export function useDeviceStorageDetail(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.devices.storageDetail(deviceId),
    queryFn: async () => {
      const res = await fetchDeviceStorage(deviceId, false);
      return res.data as DeviceStorageDetail[];
    },
    enabled: deviceId > 0
  });
}

export function useCreateStorage(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StorageRequest) =>
      post<DeviceStorageDetail>(`/devices/${deviceId}/storage`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storage(deviceId) });
    }
  });
}

export function useUpdateStorage(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ storageId, data }: { storageId: number; data: Partial<StorageRequest> }) =>
      put<DeviceStorageDetail>(`/storage/${storageId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storage(deviceId) });
    }
  });
}

export function useDeleteStorage(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (storageId: number) => del<void>(`/storage/${storageId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storage(deviceId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storageDetail(deviceId) });
    }
  });
}

interface BatchDeleteStorageRequest {
  storage_ids: number[];
}

export function useBatchDeleteStorage(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchDeleteStorageRequest) =>
      del<{ deleted: number[]; not_found: number[] }>(`/devices/${deviceId}/storage/batch`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storage(deviceId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storageDetail(deviceId) });
    }
  });
}

export function useDeleteAllStorage(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => del<void>(`/devices/${deviceId}/storage`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.storage(deviceId) });
    }
  });
}

export function useValidateSerial() {
  return useMutation({
    mutationFn: (serial_number: string) =>
      post<{ is_valid: boolean; message: string }>('/advanced/storage/validate-serial', {
        serial_number
      })
  });
}
