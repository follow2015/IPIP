/**
 * VLAN 服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 关联查询（按机房获取VLAN列表）仍手写
 * 对齐后端 /api/vlans/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import { useInvalidatingMutation } from '@/hooks/useInvalidatingMutation';
import type { VLAN } from '@/types/models';
import type { PaginationParams } from '@/types/api';
import type { VLANCreate, VLANUpdate } from '@/types/api-bridge';


export interface VLANQueryParams extends PaginationParams {
  room_id?: number;
  device_id?: number;
  status?: number;
}


export type CreateVLANRequest = VLANCreate;


export type UpdateVLANRequest = VLANUpdate & { id: number };


const vlanHooks = createCrudHooks<VLAN, CreateVLANRequest, UpdateVLANRequest, VLANQueryParams>({
  basePath: '/vlans',
  queryKey: queryKeys.vlans.all,
});

export const useVLANList   = vlanHooks.useList;
export const useVLANDetail = vlanHooks.useDetail;
export const useCreateVLAN = vlanHooks.useCreate;
export const useUpdateVLAN = vlanHooks.useUpdate;
export const useDeleteVLAN = vlanHooks.useDelete;


export function useVLANsByRoom(roomId: number) {
  return useQuery({
    queryKey: queryKeys.vlans.byRoom(roomId),
    queryFn: async () => {
      const res = await get<VLAN[]>(`/vlans/room/${roomId}`);
      return res.data;
    },
    enabled: roomId > 0,
  });
}


export function useVLANsByDevice(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.vlans.byDevice(deviceId),
    queryFn: async () => {
      const res = await get<VLAN[]>(`/devices/${deviceId}/vlans`);
      return res.data;
    },
    enabled: deviceId > 0,
  });
}


export function useUpdateVLANMembers(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vlanId, portIds }: { vlanId: number; portIds: number[] }) =>
      put<VLAN>(`/devices/${deviceId}/vlans/${vlanId}/members`, { port_ids: portIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.vlans.byDevice(deviceId) });
      
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    },
  });
}


interface CreateDeviceVLANRequest {
  vlan_id: number;
  name: string;
  purpose?: string | null;
  subnet_id?: number | null;
  status?: number;
}


export function useCreateDeviceVLAN(deviceId: number) {
  return useInvalidatingMutation(
    (data: CreateDeviceVLANRequest) =>
      post<VLAN>(`/devices/${deviceId}/vlans`, data),
    queryKeys.vlans.byDevice(deviceId),
  );
}


export const useCreateVLANLegacy = vlanHooks.useCreate;


export function useUpdateDeviceVLAN(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vlanId, data }: { vlanId: number; data: Partial<Pick<VLAN, 'purpose' | 'name' | 'status'>> }) =>
      put<VLAN>(`/devices/${deviceId}/vlans/${vlanId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.vlans.byDevice(deviceId) });
    },
  });
}
