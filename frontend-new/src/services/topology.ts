/**
 * 网络拓扑服务
 * - 网络层拓扑（交换机 + N2N 互联）
 * - 设备层拓扑（交换机 + 服务器 + N2N + D2N）
 * - 自动推断拓扑字段
 * 对齐后端 /api/topology/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post } from './api-client';
import { queryKeys } from './query-keys';
import type {
  TopologyNode,
  TopologyEdge,
  TopologyStats,
  TopologyAutoDetectChange,
} from '@/types/models';


export interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  stats: TopologyStats;
}

export interface NetworkTopologyParams {
  room_id?: number;
  virtual_room_id?: number;
  layer?: number;
  include_offline?: boolean;
}

export interface DeviceTopologyParams {
  room_id?: number;
  virtual_room_id?: number;
  cabinet_id?: number;
  switch_device_id?: number;
}

export interface AutoDetectParams {
  room_id: number;
  dry_run?: boolean;
  force?: boolean;
}

export interface AutoDetectResult {
  changes: TopologyAutoDetectChange[];
  dry_run: boolean;
}


async function fetchNetworkTopology(params?: NetworkTopologyParams): Promise<TopologyData> {
  const res = await get<TopologyData>('/topology/network', params as Record<string, unknown>);
  return res.data;
}

async function fetchDeviceTopology(params?: DeviceTopologyParams): Promise<TopologyData> {
  const res = await get<TopologyData>('/topology/device', params as Record<string, unknown>);
  return res.data;
}

async function triggerAutoDetect(params: AutoDetectParams): Promise<AutoDetectResult> {
  const res = await post<AutoDetectResult, AutoDetectParams>('/topology/auto-detect', params);
  return res.data;
}


export function useNetworkTopology(params?: NetworkTopologyParams) {
  return useQuery({
    queryKey: queryKeys.topology.network(params),
    queryFn: () => fetchNetworkTopology(params),
    staleTime: 5 * 60 * 1000, // 5 分钟缓存
    enabled: params !== undefined && Object.values(params).some(v => v !== undefined),
  });
}

export function useDeviceTopology(params?: DeviceTopologyParams) {
  return useQuery({
    queryKey: queryKeys.topology.device(params),
    queryFn: () => fetchDeviceTopology(params),
    staleTime: 5 * 60 * 1000,
    enabled: params !== undefined && Object.values(params).some(v => v !== undefined),
  });
}

export function useAutoDetectTopology() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: triggerAutoDetect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topology.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
    },
  });
}
