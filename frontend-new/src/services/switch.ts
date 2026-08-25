/**
 * 网络设备服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 同步、端口详情、SSH 操作仍手写
 * 对齐后端 /api/switch/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import { useInvalidatingMutation } from '@/hooks/useInvalidatingMutation';
import type {
  Switch,
  SwitchPortDetail,
  SwitchWithPortsResponse,
  PortConfigResult,
  SwitchPortIP
} from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';


interface SwitchQueryParams extends PaginationParams {
  search?: string;
  room_id?: number;
  cabinet_id?: number;
  switch_role?: number;
  device_type?: string;
  
  has_ssh?: boolean;
}

interface CreateSwitchRequest {
  name: string;
  ip: string;
  port?: number;
  username?: string;
  password?: string;
  protocol?: string;
  device_type?: string;
  device_model?: string;
  switch_role?: number;
  layer?: number;
  room_id?: number;
  authentication_method?: string;
  has_ssh?: boolean;
}

interface UpdateSwitchRequest {
  
  id: number;
  data: Partial<CreateSwitchRequest>;
}


interface PortRef {
  switchId: number;
  port: string;
}

interface PortSpeedPayload {
  inbound_speed: number;
  outbound_speed: number;
}

interface PortVlanPayload {
  vlan_id: number;
  mode: 'access' | 'trunk';
  allowed_vlans?: number[] | null;
}

interface PortIPPayload {
  ip_address: string;
  subnet_mask: string;
  is_secondary?: boolean;
}


const switchHooks = createCrudHooks<Switch, CreateSwitchRequest, UpdateSwitchRequest>({
  basePath: '/switch',
  queryKey: queryKeys.switches.all,
  getId: (data) => data.id,
  toUpdatePayload: (data) => data.data
});

export const useSwitchDetail = switchHooks.useDetail;
export const useSwitchSuspenseDetail = switchHooks.useSuspenseDetail;
export const useCreateSwitch = switchHooks.useCreate;
export const useUpdateSwitch = switchHooks.useUpdate;
export const useDeleteSwitch = switchHooks.useDelete;


export function useSwitchList(params?: SwitchQueryParams) {
  return useQuery({
    queryKey: [...queryKeys.switches.all, 'list', params],
    queryFn: async () => {
      const res = await get<PaginatedData<Switch>>(
        '/switch/list',
        params as Record<string, unknown>
      );
      return res.data;
    }
  });
}


export function useSwitchWithPorts(id: number, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.switches.withPorts(id),
    queryFn: async () => {
      try {
        const res = await get<SwitchWithPortsResponse>(`/switch/${id}`);
        return res.data;
      } catch (err: unknown) {
        
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    enabled: options?.enabled ?? id > 0
  });
}


export function useSyncSwitchInfo() {
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await post<null>(`/switch/${id}/collect_info`);
      return res.data;
    }
  });
}


export function useSwitchPortDetail(switchId: number, port: string, enabled: boolean = false) {
  return useQuery({
    queryKey: queryKeys.switches.portDetail(switchId, port),
    queryFn: async () => {
      const res = await get<SwitchPortDetail>(
        `/switch/${switchId}/ports/${encodeURIComponent(port)}`
      );
      return res.data;
    },
    enabled: enabled && switchId > 0 && !!port
  });
}


export function useSyncSwitchPorts() {
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await post<null>(`/switch/${id}/sync_ports`);
      return res.data;
    }
  });
}


export function useSyncSwitch() {
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await post<null>(`/switch/${id}/scan`);
      return res.data;
    }
  });
}


export function useUpdatePortCustomer() {
  return useInvalidatingMutation(
    ({
      switchId,
      port,
      data
    }: {
      switchId: number;
      port: string;
      data: { customer_id: number | null; description?: string };
    }) => put<null>(`/switch/${switchId}/ports/${encodeURIComponent(port)}`, data),
    queryKeys.switches.all
  );
}


export function useFetchPortConfig() {
  return useMutation({
    mutationFn: ({ switchId, port }: PortRef) =>
      get<PortConfigResult>(`/switch/${switchId}/ports/${encodeURIComponent(port)}/config`)
  });
}


export function useRefreshPortConfig() {
  return useMutation({
    mutationFn: ({ switchId, port }: PortRef) =>
      get<PortConfigResult>(`/switch/${switchId}/ports/${encodeURIComponent(port)}/refresh`)
  });
}


export function useSyncMembers() {
  return useMutation({
    mutationFn: async (deviceId: number) => {
      const res = await post<null>(`/switch/${deviceId}/sync_members`);
      return res.data;
    }
  });
}


export function useSwitchPortNames(switchId: number) {
  return useQuery({
    queryKey: [...queryKeys.switches.detail(switchId), 'port_names'],
    queryFn: async () => {
      const res = await get<string[]>(`/switch/${switchId}/ports_list`);
      return res.data;
    },
    enabled: switchId > 0
  });
}


export interface ScanProgress {
  room_id: number;
  total: number;
  completed: number;
  failed: number;
  phase: string;
  elapsed_seconds: number;
  eta_seconds: number;
  
  reason?: string;
}


export function useScanRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roomId: number) => post<{ message: string }>(`/switch/room/${roomId}/scan`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
    }
  });
}


export function useScanProgress(roomId: number, enabled: boolean = false) {
  const query = useQuery({
    queryKey: [...queryKeys.switches.all, 'scan-progress', roomId],
    queryFn: async () => {
      const res = await get<{ progress: ScanProgress | null }>(
        `/switch/room/${roomId}/scan/progress`
      );
      return res.data.progress;
    },
    enabled: enabled && roomId > 0,
    refetchInterval: (query) => {
      const p = query.state.data;
      
      if (p && p.total > 0 && p.phase !== '完成') return 2000;
      return false;
    },
    refetchIntervalInBackground: true
  });

  return query;
}


export {
  useLinkAggregationGroups,
  useAllLinkAggregationGroups,
  useCreateLinkAggregationGroup,
  useDeleteLinkAggregationGroup,
  type LinkAggregationGroup,
  type LinkAggregationGroupWithDevice
} from './link-aggregation';


export function useGlobalScanStatus() {
  return useQuery({
    queryKey: [...queryKeys.switches.all, 'scan-status'],
    queryFn: async () => {
      const res = await get<Record<string, unknown>>('/switch/scan/status');
      return res.data;
    }
  });
}


export function usePortIPs(switchId: number, port: string, enabled: boolean = false) {
  return useQuery({
    queryKey: [...queryKeys.switches.portDetail(switchId, port), 'ips'],
    queryFn: async () => {
      const res = await get<SwitchPortIP[]>(
        `/switch/${switchId}/ports/${encodeURIComponent(port)}/ip`
      );
      return res.data;
    },
    enabled: enabled && switchId > 0 && !!port
  });
}


export interface BatchPortActionRequest {
  action: string;
  ports?: string[];
  port_range?: string;
  params?: Record<string, unknown>;
}


export interface BatchPortActionResult {
  task_id: string;
  action: string;
  status: string;
  port_count?: number;
}


export function useBatchPortAction() {
  return useMutation({
    mutationFn: async ({ switchId, data }: { switchId: number; data: BatchPortActionRequest }) => {
      const res = await post<BatchPortActionResult>(`/switch/${switchId}/ports/batch-action`, data);
      return res.data;
    }
  });
}


export interface BatchUpdateSwitchRequest {
  device_ids: number[];
  updates: {
    port?: number;
    protocol?: string;
    username?: string;
    password?: string;
    device_type?: string;
    switch_role?: number;
    layer?: number;
    authentication_method?: string;
  };
}


export interface BatchUpdateSwitchResult {
  success_count: number;
  failed_count: number;
  success_ids: number[];
  failed_items: { device_id: number; error: string }[];
}


export function useBatchUpdateSwitch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: BatchUpdateSwitchRequest) => {
      const res = await put<BatchUpdateSwitchResult>('/switch/batch-update', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
    }
  });
}
