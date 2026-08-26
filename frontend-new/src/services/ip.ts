/**
 * IP 管理服务
 * 对齐后端 /api/ip/* 端点
 * 包含：CRUD、封禁/解封、批量封禁、状态统计、Ping/扫描
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put } from './api-client';
import { queryKeys } from './query-keys';
import type { IPAddress, IPAddressDetail, IPScanResult, PingResult } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';


export interface IPQueryParams extends PaginationParams {
  search?: string;
  status?: number;
  room_id?: number;
  customer_id?: number;
  switch_id?: number;
}

interface IPCustomerRequest {
  customer_id: number | null;
}

interface BanRequest {
  ip_address: string;
  room_id?: number;
}

interface BatchBanRequest {
  ip_list: string[];
  room_id?: number;
}

interface BatchUnbanRequest {
  ip_list: string[];
  room_id?: number;
}

interface BatchUpdateIPCustomerRequest {
  ip_list: string[];
  customer_id: number | null;
  room_id?: number;
}

interface BatchUpdateIPNotesRequest {
  ip_list: string[];
  notes: string;
  room_id?: number;
}

interface BanResult {
  ip_address: string;
  switch_id: number;
  switch_ip: string;
}

interface BanStatusResult {
  ip_address: string;
  is_banned: boolean;
  status: number;
  updated_at: string | null;
}

interface IPStatisticsResult {
  total: number;
  active: number;
  inactive: number;
  blocked: number;
  unused: number;
}


export function useIPList(params?: IPQueryParams) {
  return useQuery({
    queryKey: queryKeys.ip.list(params),
    queryFn: async () => {
      const res = await get<PaginatedData<IPAddress>>('/ip/list', params);
      return res.data;
    }
  });
}

export function useIPDetail(address: string) {
  return useQuery({
    queryKey: queryKeys.ip.detail(address),
    queryFn: async () => {
      const res = await get<IPAddressDetail>(`/ip/${encodeURIComponent(address)}`);
      return res.data;
    },
    enabled: !!address
  });
}

export function useScanIP() {
  return useMutation({
    mutationFn: (address: string) => post<IPScanResult>(`/ip/${encodeURIComponent(address)}/scan`)
  });
}


export function usePingIP() {
  return useMutation({
    mutationFn: (address: string) => post<PingResult>(`/ip/${encodeURIComponent(address)}/ping`)
  });
}

export function useDetectIPStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (address: string) =>
      post<{ ip_address: string; status: number; status_text: string }>(
        `/ip/${encodeURIComponent(address)}/detect`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useUpdateIPCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ address, data }: { address: string; data: IPCustomerRequest }) =>
      put<IPAddressDetail, IPCustomerRequest>(`/ip/${encodeURIComponent(address)}/customer`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useIPNotes(address: string) {
  return useQuery({
    queryKey: [...queryKeys.ip.detail(address), 'notes'],
    queryFn: async () => {
      const res = await get<{ notes: string }>(`/ip/${encodeURIComponent(address)}/notes`);
      return res.data;
    },
    enabled: !!address
  });
}

export function useUpdateIPNotes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ address, notes }: { address: string; notes: string }) =>
      put<IPAddressDetail>(`/ip/${encodeURIComponent(address)}/notes`, { notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}


export function useBanIP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BanRequest) => post<BanResult>('/ip/ban', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useUnbanIP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BanRequest) => post<BanResult>('/ip/unban', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useBatchBanIP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchBanRequest) => post<Record<string, unknown>>('/ip/ban/batch', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useBatchUnbanIP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchUnbanRequest) => post<Record<string, unknown>>('/ip/unban/batch', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useBatchUpdateIPCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchUpdateIPCustomerRequest) =>
      post<{ updated: number }>('/ip/batch/customer', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useBatchUpdateIPNotes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchUpdateIPNotesRequest) =>
      post<{ updated: number }>('/ip/batch/notes', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}

export function useBanStatus(address: string, roomId: number) {
  return useQuery({
    queryKey: [...queryKeys.ip.detail(address), 'ban_status', roomId],
    queryFn: async () => {
      const res = await get<BanStatusResult>(`/ip/${encodeURIComponent(address)}/ban_status`, {
        room_id: roomId
      });
      return res.data;
    },
    enabled: !!address && roomId > 0
  });
}


export function useIPStatistics(roomId?: number, search?: string) {
  return useQuery({
    queryKey: [...queryKeys.ip.all, 'statistics', roomId, search],
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (roomId) params.room_id = roomId;
      if (search) params.search = search;
      const res = await get<IPStatisticsResult>('/ip/statistics', params);
      return res.data;
    }
  });
}
