/**
 * 机柜服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 关联查询（设备列表、利用率、U位、统计、布局）仍手写
 * 对齐后端 /api/cabinets/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { Cabinet, Device, CabinetUtilization, CabinetUsageMap, CabinetStats } from '@/types/models';
import type { PaginationParams } from '@/types/api';
import type { CabinetCreate, CabinetUpdate } from '@/types/api-bridge';


export interface CabinetQueryParams extends PaginationParams {
  search?: string;
  room_id?: number;
  cabinet_number?: string;
  status?: number;
}


export interface BatchCreateCabinetResponse {
  created: Cabinet[];
  failed: string[];
  errors: Record<string, string>;
  created_count: number;
  failed_count: number;
}


type CreateCabinetRequest = CabinetCreate;


type UpdateCabinetRequest = CabinetUpdate & { id: number };


const cabinetHooks = createCrudHooks<Cabinet, CreateCabinetRequest, UpdateCabinetRequest, CabinetQueryParams>({
  basePath: '/cabinets',
  queryKey: queryKeys.cabinets.all,
});

export const useCabinetList   = cabinetHooks.useList;
export const useCabinetDetail = cabinetHooks.useDetail;
export const useCabinetSuspenseDetail = cabinetHooks.useSuspenseDetail;
export const useCreateCabinet = cabinetHooks.useCreate;
export const useDeleteCabinet = cabinetHooks.useDelete;


export function useUpdateCabinet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateCabinetRequest) => {
      const { id, ...payload } = data;
      return put<Cabinet>(`/cabinets/${id}`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    },
  });
}


export function useBatchCreateCabinet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateCabinetRequest) =>
      post<BatchCreateCabinetResponse, CreateCabinetRequest>('/cabinets', { ...data, batch: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    },
  });
}


export function useCabinetWithDevices(id: number) {
  return useQuery({
    queryKey: queryKeys.cabinets.withDevices(id),
    queryFn: async () => {
      const res = await get<Cabinet>(`/cabinets/${id}/with-devices`);
      return res.data;
    },
    enabled: id > 0,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}


export function useCabinetDevices(id: number) {
  return useQuery({
    queryKey: queryKeys.cabinets.devices(id),
    queryFn: async () => {
      const res = await get<Device[]>(`/cabinets/${id}/devices`);
      return res.data;
    },
    enabled: id > 0,
  });
}


export function useCabinetUtilization(id: number) {
  return useQuery({
    queryKey: queryKeys.cabinets.utilization(id),
    queryFn: async () => {
      const res = await get<CabinetUtilization>(`/cabinets/${id}/utilization`);
      return res.data;
    },
    enabled: id > 0,
  });
}


export function useCabinetUsageMap(id: number) {
  return useQuery({
    queryKey: queryKeys.cabinets.usageMap(id),
    queryFn: async () => {
      const res = await get<CabinetUsageMap>(`/cabinets/${id}/u-positions/usage-map`);
      return res.data;
    },
    enabled: id > 0,
  });
}


export function useCabinetAvailableUPositions(id: number) {
  return useQuery({
    queryKey: [...queryKeys.cabinets.all, id, 'u-positions'],
    queryFn: async () => {
      const res = await get<{
        available_positions: number[];
        total_available: number;
        usage_map: Array<{ u_position: number; is_used: boolean; is_spacing: boolean }>;
      }>(`/cabinets/${id}/u-positions`);
      return res.data?.available_positions ?? [];
    },
    enabled: id > 0,
  });
}


export function useCabinetLayout(id: number) {
  return useQuery({
    queryKey: [...queryKeys.cabinets.all, id, 'layout'],
    queryFn: async () => {
      const res = await get<{
        cabinet_id: number;
        cabinet_number: string;
        room_name: string | null;
        total_u: number;
        used_u: number;
        available_u: number;
        usage_rate: number;
        device_count: number;
        u_map: Record<number, {
          device_id: number;
          device_name: string;
          device_type: string;
          is_start: boolean;
          height_u: number;
          power: number | null;
        }>;
        available_ranges: Array<{ start: number; end: number; height: number }>;
      }>(`/cabinets/${id}/layout`);
      return res.data;
    },
    enabled: id > 0,
  });
}


export function useCabinetStats(id: number) {
  return useQuery({
    queryKey: queryKeys.cabinets.stats(id),
    queryFn: async () => {
      const res = await get<CabinetStats>(`/cabinets/${id}/stats`);
      return res.data;
    },
    enabled: id > 0,
  });
}


export function useCabinetOptions(roomId?: number, forFilter: boolean = false, statuses?: number[]) {
  return useQuery({
    queryKey: queryKeys.cabinets.options(roomId),
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (roomId) params.room_id = roomId;

      if (statuses) {
        
        params.statuses = statuses.join(',');
        params.min_available_u = 1;
      } else if (forFilter) {
        
        params.all_status = 1;
        params.min_available_u = 0;
      } else {
        
        params.min_available_u = 1;
      }

      const res = await get<Cabinet[]>('/cabinets/available', params);
      return (res.data ?? []).map((c) => ({
        label: `${c.cabinet_number} (U${c.used_u ?? 0}/${c.total_u})`,
        value: c.id,
      }));
    },
  });
}
