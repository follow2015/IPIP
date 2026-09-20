/**
 * 机房服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 关联查询（机柜列表、设备列表、统计）仍手写
 * 对齐后端 /api/rooms/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type {
  Room,
  Cabinet,
  RoomChannel,
  RoomLayoutMarker,
  RoomOverviewGroup
} from '@/types/models';
import type { PaginationParams } from '@/types/api';
import type {
  RoomChannelCreate,
  RoomChannelUpdate,
  RoomCreate,
  RoomLayoutMarkerCreate,
  RoomLayoutMarkerUpdate,
  RoomUpdate
} from '@/types/api-bridge';

interface RoomQueryParams extends PaginationParams {
  search?: string;
  name?: string;
  building?: string;
  floor?: string;
  status?: number;
}

export type CreateRoomRequest = RoomCreate;

export type UpdateRoomRequest = RoomUpdate & { id: number };


const roomHooks = createCrudHooks<Room, CreateRoomRequest, UpdateRoomRequest>({
  basePath: '/rooms',
  queryKey: queryKeys.rooms.all,
  optionsConfig: {
    path: '/rooms/all',
    labelKey: 'name',
    valueKey: 'id'
  }
});

export const useRoomList = roomHooks.useList;
export const useRoomDetail = roomHooks.useDetail;
export const useRoomSuspenseDetail = roomHooks.useSuspenseDetail;
export const useCreateRoom = roomHooks.useCreate;
export const useUpdateRoom = roomHooks.useUpdate;
export const useDeleteRoom = roomHooks.useDelete;
export const useRoomOptions = roomHooks.useOptions;


export function useRoomCabinets(roomId: number) {
  return useQuery({
    queryKey: queryKeys.rooms.cabinets(roomId),
    queryFn: async () => {
      const res = await get<Cabinet[]>(`/rooms/${roomId}/cabinets`);
      return res.data;
    },
    enabled: roomId > 0
  });
}

export function useRoomOverview() {
  return useQuery({
    queryKey: queryKeys.rooms.overview,
    queryFn: async () => {
      const res = await get<{ groups: RoomOverviewGroup[] }>('/rooms/overview');
      return res.data?.groups ?? [];
    },
    staleTime: 0
  });
}

export interface RoomNameOption {
  name: string;
  room_count: number;
}

export function useRoomNameOptions() {
  return useQuery({
    queryKey: queryKeys.rooms.nameOptions,
    queryFn: async () => {
      const res = await get<{ options: RoomNameOption[] }>('/rooms/name-options');
      return res.data?.options ?? [];
    },
    staleTime: 60 * 1000
  });
}

export function useRoomBuildings() {
  return useQuery({
    queryKey: queryKeys.rooms.buildings,
    queryFn: async () => {
      const res = await get<{ buildings: string[] }>('/rooms/buildings');
      return res.data?.buildings ?? [];
    },
    staleTime: 5 * 60 * 1000
  });
}

export function useRoomFloors(building?: string) {
  return useQuery({
    queryKey: queryKeys.rooms.floors(building),
    queryFn: async () => {
      const query = building ? `?building=${encodeURIComponent(building)}` : '';
      const res = await get<{ floors: string[] }>(`/rooms/floors${query}`);
      return res.data?.floors ?? [];
    },
    staleTime: 5 * 60 * 1000
  });
}

export function useRoomStatistics(roomId: number) {
  return useQuery({
    queryKey: queryKeys.rooms.statistics(roomId),
    queryFn: async () => {
      const res = await get<Record<string, unknown>>(`/rooms/${roomId}/statistics`);
      return res.data;
    },
    enabled: roomId > 0
  });
}


export function useRoomChannels(roomId: number) {
  return useQuery({
    queryKey: queryKeys.rooms.channels(roomId),
    queryFn: async () => {
      const res = await get<RoomChannel[]>(`/rooms/${roomId}/channels`);
      return res.data;
    },
    enabled: roomId > 0
  });
}

export function useCreateRoomChannel(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RoomChannelCreate) => post<RoomChannel>(`/rooms/${roomId}/channels`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.channels(roomId) });
    }
  });
}

export function useUpdateRoomChannel(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: number; data: RoomChannelUpdate }) =>
      put<RoomChannel>(`/rooms/${roomId}/channels/${channelId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.channels(roomId) });
    }
  });
}

export function useDeleteRoomChannel(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: number) => del<null>(`/rooms/${roomId}/channels/${channelId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.channels(roomId) });
    }
  });
}


export function useRoomLayoutMarkers(roomId: number) {
  return useQuery({
    queryKey: queryKeys.rooms.markers(roomId),
    queryFn: async () => {
      const res = await get<RoomLayoutMarker[]>(`/rooms/${roomId}/layout-markers`);
      return res.data;
    },
    enabled: roomId > 0
  });
}

export function useCreateRoomLayoutMarker(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RoomLayoutMarkerCreate) =>
      post<RoomLayoutMarker>(`/rooms/${roomId}/layout-markers`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.markers(roomId) });
    }
  });
}

export function useUpdateRoomLayoutMarker(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ markerId, data }: { markerId: number; data: RoomLayoutMarkerUpdate }) =>
      put<RoomLayoutMarker>(`/rooms/${roomId}/layout-markers/${markerId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.markers(roomId) });
    }
  });
}

export function useDeleteRoomLayoutMarker(roomId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (markerId: number) => del<null>(`/rooms/${roomId}/layout-markers/${markerId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.markers(roomId) });
    }
  });
}
