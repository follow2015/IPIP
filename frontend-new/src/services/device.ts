/**
 * 设备服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 批量操作、状态更新、位置更新、序列号生成、统计仍手写
 * 对齐后端 /api/devices/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { Device, BatchCreateResult, CloneDeviceData } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';
import type {
  DeviceCreate as OpenApiDeviceCreate,
  DeviceUpdate as OpenApiDeviceUpdate
} from '@/types/api-bridge';


export interface DeviceQueryParams extends PaginationParams {
  search?: string;
  room_id?: number;
  cabinet_id?: number;
  device_type?: string;
  device_subtype?: string;
  status?: number;
  ip?: string;
  parent_device_id?: number;
  customer_id?: number;
  is_chassis?: number;
  
  has_ssh?: boolean;
}


export interface CreateDeviceRequest extends Omit<
  OpenApiDeviceCreate,
  | 'switch_config'
  | 'node_hardware'
  | 'storage_items'
  | 'nic_ports'
  | 'auto_create_nodes'
  | 'cpu_template_id'
  | 'memory_template_id'
  | 'memory_dimm_count'
  | 'gpu_count'
  | 'gpu_template_id'
> {
  
  auto_create_nodes?: boolean;
  
  cpu_template_id?: number | null;
  
  memory_template_id?: number | null;
  
  memory_dimm_count?: number | null;
  
  gpu_count?: number | null;
  
  gpu_template_id?: number | null;
  
  switch_config?: {
    ip?: string;
    port?: number;
    username?: string;
    password?: string;
    protocol?: string;
    device_type?: string;
    switch_role?: number;
    layer?: number;
    authentication_method?: string;
    has_ssh?: boolean;
    
    uplink_device_id?: number | null;
    core_device_id?: number | null;
    port_num?: number | null;
    uplink_port_ids?: number[] | null;
  };
  
  node_hardware?: {
    cpu?: string;
    cpu_way?: number;
    cpu_cores?: number;
    cpu_template_id?: number | null;
    memory?: string;
    memory_size_gb?: number;
    memory_template_id?: number | null;
    memory_dimm_count?: number | null;
    gpu?: string;
    gpu_count?: number | null;
    gpu_template_id?: number | null;
    storage_summary?: string;
  };
  
  storage_items?: {
    template_id?: number;
    storage_type?: string;
    capacity?: string;
    interface_type?: string;
    count?: number;
    slot_number?: number;
  }[];
  
  nic_ports?: {
    template_id?: number;
    nic_number?: number;
    nic_name?: string;
    port_number?: number;
    port_name?: string;
    port_type?: string;
    port_speed?: string;
    port_status?: string;
    description?: string;
  }[];
}

export interface UpdateDeviceRequest extends Partial<CreateDeviceRequest> {
  id: number;
  
  metric_template_group_id?: number | null;
}


const deviceHooks = createCrudHooks<
  Device,
  CreateDeviceRequest,
  UpdateDeviceRequest,
  DeviceQueryParams
>({
  basePath: '/devices',
  queryKey: queryKeys.devices.all
});

export const useDeviceList = deviceHooks.useList;
export const useDeviceDetail = deviceHooks.useDetail;
export const useDeviceSuspenseDetail = deviceHooks.useSuspenseDetail;


export function useDeleteDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del<void>(`/devices/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
      
      
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.metricAlertsAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.overview });
    }
  });
}


export function useCreateDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDeviceRequest) => post<Device, CreateDeviceRequest>('/devices', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function useUpdateDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateDeviceRequest) => {
      const { id, ...payload } = data;
      return put<Device>(`/devices/${id}`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
      
      
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}


export function useDeviceStatistics() {
  return useQuery({
    queryKey: queryKeys.devices.statistics,
    queryFn: async () => {
      const res = await get<Record<string, unknown>>('/devices/statistics');
      return res.data;
    }
  });
}


export function useUpdateDeviceStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: number }) =>
      put<void>(`/devices/${id}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function useUpdateDeviceLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data
    }: {
      id: number;
      data: { cabinet_id: number; u_position?: number | null; height_u?: number | null };
    }) => put<void>(`/devices/${id}/location`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function useBatchDeleteDevices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) => post<null>('/devices/batch-delete', { ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.metricAlertsAll });
      queryClient.invalidateQueries({ queryKey: queryKeys.monitor.overview });
    }
  });
}


export function useBatchUpdateDeviceStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: number }) =>
      post<null>('/devices/batch-update-status', { device_ids: ids, status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function useBatchCreateDevices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (devices: CreateDeviceRequest[]) =>
      post<BatchCreateResult>('/devices/batch-create', { devices }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export function useCloneDevice() {
  return useMutation({
    mutationFn: (deviceId: number) => post<CloneDeviceData>(`/devices/clone/${deviceId}`)
  });
}


export interface BatchUpdateHardwareRequest {
  ids: number[];
  cpu?: string | null;
  cpu_way?: number | null;
  cpu_cores?: number | null;
  cpu_template_id?: number | null;
  memory?: string | null;
  memory_size_gb?: number | null;
  memory_template_id?: number | null;
  gpu?: string | null;
  gpu_count?: number | null;
  gpu_template_id?: number | null;
  os_version?: string | null;
  ipmi_address?: string | null;
  ipmi_username?: string | null;
  ipmi_password?: string | null;
  storage_summary?: string | null;
}


export interface BatchUpdateAssetRequest {
  ids: number[];
  auto_generate_asset_number: boolean;
  supplier?: string | null;
  supplier_contact?: string | null;
  contract_number?: string | null;
  purchase_date?: string | null;
  purchase_price?: number | null;
  invoice_number?: string | null;
  warranty_start?: string | null;
  warranty_end?: string | null;
  warranty_type?: string | null;
  online_date?: string | null;
  offline_date?: string | null;
  lifecycle_years?: number | null;
}


export function useBatchUpdateDeviceAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, ...asset }: BatchUpdateAssetRequest) =>
      post<{ updated: number; skipped: number }>('/devices/batch-update-asset', {
        ids,
        ...asset
      }),
    onSuccess: (_, variables) => {
      variables.ids.forEach((id) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(id) });
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export interface BatchUpdateConfigRequest {
  ids: number[];
  main?: {
    brand?: string | null;
    device_model?: string | null;
    power?: number | null;
    responsible_person?: number | null;
    customer_id?: number | null;
  };
  hardware?: Record<string, unknown>;
  
  storage_items?: {
    template_id?: number;
    storage_type?: string;
    capacity?: string;
    interface_type?: string;
    count?: number;
    slot_number?: number;
  }[];
  nic_ports?: Record<string, unknown>[];
  switch_config?: Record<string, unknown>;
  switch_ports?: Record<string, unknown>[];
}

export function useBatchUpdateDeviceConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BatchUpdateConfigRequest) =>
      post<{
        updated: number;
        skipped: number;
        nic_created: number;
        port_created: number;
        storage_created?: number;
      }>('/devices/batch-update-config', payload),
    onSuccess: (_, variables) => {
      variables.ids.forEach((id) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(id) });
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export interface SwapNodePositionsRequest {
  source_position: number;
  target_position: number;
}
export function useSwapNodePositions(chassisId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SwapNodePositionsRequest) =>
      post<{ swapped: boolean; source: number; target: number; exchanged: boolean }>(
        `/devices/${chassisId}/swap-node-positions`,
        payload
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(chassisId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export function useBatchResetDeviceAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) =>
      post<{ updated: number; skipped: number }>('/devices/batch-reset-asset', { ids }),
    onSuccess: (_, ids) => {
      ids.forEach((id) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(id) });
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export function useBatchUpdateDeviceHardware() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, ...hardware }: BatchUpdateHardwareRequest) =>
      post<{ updated: number; skipped: number }>('/devices/batch-update-hardware', {
        ids,
        ...hardware
      }),
    onSuccess: (_, variables) => {
      
      variables.ids.forEach((id) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(id) });
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export function useGenerateSerialNumber() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params?: { prefix?: string; format_type?: string; length?: number }) =>
      post<{ serial_number: string }>('/devices/generate-serial-number', params ?? {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export interface DeletedDeviceQueryParams extends PaginationParams {
  start_date?: string;
  end_date?: string;
  room_id?: number;
  cabinet_id?: number;
  device_type?: string;
  search?: string;
}


export function useDeletedDeviceList(params: DeletedDeviceQueryParams) {
  return useQuery({
    queryKey: [...queryKeys.devices.all, 'deleted', params],
    queryFn: async () => {
      const res = await get<PaginatedData<Device>>('/devices/deleted', params);
      return res.data;
    }
  });
}


export function useRestoreDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      cabinet_id,
      u_position
    }: {
      id: number;
      cabinet_id?: number;
      u_position?: number;
    }) => post<Record<string, unknown>>(`/devices/${id}/restore`, { cabinet_id, u_position }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function useBatchRestoreDevices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      device_ids,
      cabinet_id,
      u_position
    }: {
      device_ids: number[];
      cabinet_id?: number;
      u_position?: number;
    }) =>
      post<Record<string, unknown>>('/devices/batch-restore', {
        device_ids,
        cabinet_id,
        u_position
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
    }
  });
}


export function usePermanentDeleteDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del<void>(`/devices/${id}/permanent`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export function useBatchPermanentDeleteDevices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (device_ids: number[]) =>
      post<Record<string, unknown>>('/devices/batch-permanent-delete', { device_ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
    }
  });
}


export interface DeviceSearchResult {
  id: number;
  device_name: string;
  management_ip: string | null;
}


export async function searchDevicesForLink(keyword: string): Promise<DeviceSearchResult[]> {
  const res = await get<{ items: DeviceSearchResult[]; total: number }>('/devices', {
    search: keyword,
    per_page: 50
  });
  return res.data?.items ?? [];
}
