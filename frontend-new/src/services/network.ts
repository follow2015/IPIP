/**
 * 网络管理服务
 * 对齐后端 /api/network/* 端点：
 * - GET  /api/network/list        — 网段列表（分页+过滤）
 * - DELETE /api/network/<ip_network> — 删除网段
 * - PUT  /api/network/<ip_network>/customer — 更新网段客户
 * - GET  /api/network/<network>/ips — 网段详情（含 IP 列表+路由信息）
 * - POST /api/ip/scan/network     — 扫描网段/所有网段
 * - GET  /api/network/routes      — 路由列表
 * - GET  /api/network/info        — CIDR网段信息计算
 * - GET  /api/network/usage       — 网段使用率
 * - POST /api/network/scan/<room_id> — 全量扫描（异步）
 * - GET  /api/network/scan/status/<room_id> — 扫描进度
 */
import { useQuery, useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';
import type { IPNetwork, NetworkDetailResponse, NetworkInfo } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';

interface NetworkQueryParams extends PaginationParams {
  room_id?: number;
  switch_id?: number;
  customer_id?: number;
  search?: string;
  route_type?: string; // 路由类型过滤（RouteNotes 枚举值）
  notes?: string; // 兼容旧参数名
  switch_name?: string;
  customer_name?: string;
}

interface NetworkDetailParams {
  page?: number;
  page_size?: number;
  room_id?: number;
  [key: string]: unknown;
}

interface DeleteNetworkRequest {
  network_id: number;
}

interface UpdateNetworkCustomerRequest {
  network_id: number;
  customer_id: number | null;
  room_id?: number;
  force?: boolean;
}

interface RouteQueryParams {
  switch_id?: number;
  room_id?: number;
  notes?: number;
}

interface RouteItem {
  id: number;
  switch_id: number;
  destination: string;
  ip_network: string;
  nexthop: string | null;
  route_type: number | null;
  interface: string | null;
  port: string | null;
  notes: string | null;
  room_id: number;
  customer_id: number | null;
  updated_at: string | null;
}

interface NetworkUsageResult {
  cidr: string;
  total_ips: number;
  used_ips: number;
  usage_rate: number;
  available_ips: number;
}

interface ScanStatusResult {
  phase: string;
  detail: string;
  total?: number;
  completed?: number;
  failed?: number;
  elapsed_seconds?: number;
  eta_seconds?: number;
  reason?: string;
}


export function useNetworkList(params?: NetworkQueryParams) {
  return useQuery({
    queryKey: queryKeys.networks.list(params),
    queryFn: async () => {
      const res = await get<PaginatedData<IPNetwork>>('/network/list', params);
      return res.data;
    }
  });
}

export function useNetworkDetail(network: string, params?: NetworkDetailParams) {
  return useQuery({
    queryKey: queryKeys.networks.detail(network, params),
    queryFn: async () => {
      const res = await get<NetworkDetailResponse>(
        `/network/${encodeURIComponent(network)}/ips`,
        params
      );
      return res.data;
    },
    enabled: !!network
  });
}

export function useNetworkSuspenseDetail(network: string, params?: NetworkDetailParams) {
  return useSuspenseQuery({
    queryKey: queryKeys.networks.detail(network, params),
    queryFn: async () => {
      const res = await get<NetworkDetailResponse>(
        `/network/${encodeURIComponent(network)}/ips`,
        params
      );
      return res.data;
    }
  });
}

export function useDeleteNetwork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ipNetwork, networkId }: { ipNetwork: string; networkId: number }) =>
      del<void>(`/network/${encodeURIComponent(ipNetwork)}`, { network_id: networkId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
    }
  });
}

export function useUpdateNetworkCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ipNetwork,
      data
    }: {
      ipNetwork: string;
      data: UpdateNetworkCustomerRequest;
    }) => {
      return put<void>(`/network/${encodeURIComponent(ipNetwork)}/customer`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useScanNetwork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ipNetwork, roomId }: { ipNetwork: string; roomId: number }) =>
      post<{ message: string }>('/ip/scan/network', {
        ip_network: ipNetwork,
        room_id: roomId
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
    }
  });
}


export function useNetworkRoutes(params?: RouteQueryParams) {
  return useQuery({
    queryKey: [...queryKeys.networks.all, 'routes', params],
    queryFn: async () => {
      const res = await get<RouteItem[]>('/network/routes', params as Record<string, unknown>);
      return res.data;
    }
  });
}


export function useNetworkInfo(cidr: string) {
  return useQuery({
    queryKey: [...queryKeys.networks.all, 'info', cidr],
    queryFn: async () => {
      const res = await get<NetworkInfo>('/network/info', { cidr });
      return res.data;
    },
    enabled: !!cidr
  });
}


export function useNetworkUsage(cidr: string) {
  return useQuery({
    queryKey: [...queryKeys.networks.all, 'usage', cidr],
    queryFn: async () => {
      const res = await get<NetworkUsageResult>('/network/usage', { cidr });
      return res.data;
    },
    enabled: !!cidr
  });
}


export function useTriggerFullScan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roomId: number) =>
      post<{ room_id: number; status: string }>(`/network/scan/${roomId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
    }
  });
}

export function useFullScanStatus(roomId: number, enabled: boolean = false) {
  return useQuery({
    queryKey: [...queryKeys.networks.all, 'scan-status', roomId],
    queryFn: async () => {
      const res = await get<ScanStatusResult>(`/network/scan/status/${roomId}`);
      return res.data;
    },
    enabled: enabled && roomId > 0,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return 3000;
      if (d.phase === '完成' || d.phase === 'failed' || d.phase === 'unknown') return false;
      if (d.elapsed_seconds && d.elapsed_seconds > 600) return false;
      return 3000;
    },
    refetchIntervalInBackground: true
  });
}
