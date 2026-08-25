/**
 * 机房服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 关联查询（机柜列表、设备列表、统计）仍手写
 * 对齐后端 /api/rooms/* 端点
 */
import { useQuery } from '@tanstack/react-query';
import { get } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { Room, Cabinet } from '@/types/models';
import type { PaginationParams } from '@/types/api';
import type { RoomCreate, RoomUpdate } from '@/types/api-bridge';


interface RoomQueryParams extends PaginationParams {
  search?: string;
  name?: string;
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
    valueKey: 'id',
  },
});

export const useRoomList   = roomHooks.useList;
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
    enabled: roomId > 0,
  });
}


export function useRoomStatistics(roomId: number) {
  return useQuery({
    queryKey: queryKeys.rooms.statistics(roomId),
    queryFn: async () => {
      const res = await get<Record<string, unknown>>(`/rooms/${roomId}/statistics`);
      return res.data;
    },
    enabled: roomId > 0,
  });
}
