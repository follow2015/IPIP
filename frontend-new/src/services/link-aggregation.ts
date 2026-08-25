/**
 * 链路聚合组服务（从 switch.ts 拆出）
 * - 按设备查询 / 全局查询 / 创建 / 删除
 * 对齐后端 /api/switch/<id>/port-channels + /api/link-aggregation 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';
import { useInvalidatingMutation } from '@/hooks/useInvalidatingMutation';
import type { LinkAggregationGroup } from '@/types/models';
import type { PaginatedData } from '@/types/api';
export type { LinkAggregationGroup } from '@/types/models';


export interface LinkAggregationGroupWithDevice extends LinkAggregationGroup {
  device_name: string;
  room_id: number | null;
  has_ssh?: boolean;
}


export function useLinkAggregationGroups(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.linkAggregation.byDevice(deviceId),
    queryFn: async () => {
      const res = await get<LinkAggregationGroup[]>(`/devices/${deviceId}/port-channels`);
      return res.data;
    },
    enabled: deviceId > 0,
  });
}


export interface LAGListParams {
  page?: number;
  per_page?: number;
  search?: string;
  room_id?: number;
  device_id?: number;
}


export function useAllLinkAggregationGroups(params?: LAGListParams) {
  return useQuery({
    queryKey: queryKeys.linkAggregation.allGlobal(params?.room_id, params),
    queryFn: async () => {
      const res = await get<PaginatedData<LinkAggregationGroupWithDevice>>('/link-aggregation', params as Record<string, unknown>);
      return res.data;
    },
  });
}


export function useCreateLinkAggregationGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId: d, data }: { deviceId: number; data: { lag_name: string; lag_type: 'lacp' | 'static'; member_ports?: string[] } }) =>
      post<LinkAggregationGroup>(`/devices/${d}/port-channels`, data),
    onSuccess: (_data, variables) => {
      const d = variables.deviceId;
      queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.all });
      
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(d) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(d) });
    },
  });
}


export function useDeleteLinkAggregationGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId: d, lagId }: { deviceId: number; lagId: number }) =>
      del<null>(`/devices/${d}/port-channels/${lagId}`),
    onSuccess: (_data, variables) => {
      const d = variables.deviceId;
      queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.all });
      
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(d) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(d) });
    },
  });
}


export function useUpdateLAGMembers(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lagId, portIds }: { lagId: number; portIds: number[] }) =>
      put<LinkAggregationGroup>(`/devices/${deviceId}/port-channels/${lagId}/members`, { port_ids: portIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.byDevice(deviceId) });
      
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
    },
  });
}


export function useUpdateLinkAggregationGroup(deviceId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lagId, data }: { lagId: number; data: Partial<Pick<LinkAggregationGroup, 'purpose' | 'lag_type' | 'algorithm'>> }) =>
      put<LinkAggregationGroup>(`/devices/${deviceId}/port-channels/${lagId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.byDevice(deviceId) });
    },
  });
}
