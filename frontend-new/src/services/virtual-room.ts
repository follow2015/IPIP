/**
 * 虚拟机房服务
 * - CRUD + 扫描 + 进度查询
 * 对齐后端 /api/virtual-rooms/* 端点
 * 注意：api-client baseURL 已包含 /api，路径无需再加 /api 前缀
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import type { VirtualRoom, ScanProgress } from '@/types/models';
import type { PaginationParams, PaginatedData } from '@/types/api';


const fetchVirtualRooms = (params?: PaginationParams) =>
  get<PaginatedData<VirtualRoom>>('/virtual-rooms', params as Record<string, unknown>);

const fetchVirtualRoom = (id: number) =>
  get<VirtualRoom>(`/virtual-rooms/${id}`);

const createVirtualRoom = (data: { name: string; description?: string; device_ids: number[] }) =>
  post<VirtualRoom>('/virtual-rooms', data);

const updateVirtualRoom = (id: number, data: { name?: string; description?: string }) =>
  put<VirtualRoom>(`/virtual-rooms/${id}`, data);

const deleteVirtualRoom = (id: number) =>
  del(`/virtual-rooms/${id}`);

const updateVirtualRoomMembers = (id: number, device_ids: number[]) =>
  put<VirtualRoom>(`/virtual-rooms/${id}/members`, { device_ids });

const scanVirtualRoom = (id: number) =>
  post<{ message: string }>(`/virtual-rooms/${id}/scan`);

const fetchVirtualRoomScanProgress = (id: number) =>
  get<{ progress: ScanProgress | null }>(`/virtual-rooms/${id}/scan/progress`);


export const virtualRoomKeys = {
  all: ['virtual-rooms'] as const,
  list: (params?: PaginationParams) => [...virtualRoomKeys.all, 'list', params] as const,
  detail: (id: number) => [...virtualRoomKeys.all, 'detail', id] as const,
  scanProgress: (id: number) => [...virtualRoomKeys.all, 'scan-progress', id] as const,
};


export function useVirtualRooms(params?: PaginationParams) {
  return useQuery({
    queryKey: virtualRoomKeys.list(params),
    queryFn: async () => {
      const res = await fetchVirtualRooms(params);
      return res.data;
    },
  });
}

export function useVirtualRoom(id: number, enabled = true) {
  return useQuery({
    queryKey: virtualRoomKeys.detail(id),
    queryFn: async () => {
      const res = await fetchVirtualRoom(id);
      return res.data;
    },
    enabled,
  });
}

export function useCreateVirtualRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createVirtualRoom,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: virtualRoomKeys.all });
    },
  });
}

export function useUpdateVirtualRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; description?: string } }) =>
      updateVirtualRoom(id, data),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: virtualRoomKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: virtualRoomKeys.all });
    },
  });
}

export function useDeleteVirtualRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteVirtualRoom,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: virtualRoomKeys.all });
    },
  });
}

export function useUpdateVirtualRoomMembers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, device_ids }: { id: number; device_ids: number[] }) =>
      updateVirtualRoomMembers(id, device_ids),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: virtualRoomKeys.detail(id) });
    },
  });
}

export function useScanVirtualRoom() {
  return useMutation({
    mutationFn: scanVirtualRoom,
  });
}

export function useVirtualRoomScanProgress(id: number, enabled = true) {
  return useQuery({
    queryKey: virtualRoomKeys.scanProgress(id),
    queryFn: async () => {
      const res = await fetchVirtualRoomScanProgress(id);
      return res.data;
    },
    enabled,
    refetchInterval: (query) => {
      const progress = query.state.data?.progress;
      if (!progress || progress.phase === '完成' || progress.phase === 'failed') return false;
      return 2000; // 2s 轮询
    },
  });
}
