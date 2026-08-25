/**
 * 客户服务
 * - 标准 CRUD 通过 createCrudHooks 生成
 * - 关联查询（机柜、设备、资产、统计）仍手写
 * 对齐后端 /api/customers/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { get, post } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { Customer, CustomerAssets, Cabinet, Device } from '@/types/models';
import type { PaginationParams, PaginatedData } from '@/types/api';
import type { CustomerCreate, CustomerUpdate } from '@/types/api-bridge';
import type { SelectOption } from './crud-factory';


interface CustomerQueryParams extends PaginationParams {
  search?: string;
  customer_name?: string;
  customer_status?: number;
}


export type CreateCustomerRequest = CustomerCreate;


export type UpdateCustomerRequest = CustomerUpdate & { id: number };


const customerHooks = createCrudHooks<Customer, CreateCustomerRequest, UpdateCustomerRequest>({
  basePath: '/customers',
  queryKey: queryKeys.customers.all,
  optionsConfig: {
    paginated: true,
    labelKey: 'customer_name',
    valueKey: 'id'
  }
});

export const useCustomerList = customerHooks.useList;
export const useCustomerDetail = customerHooks.useDetail;
export const useCustomerSuspenseDetail = customerHooks.useSuspenseDetail;
export const useCreateCustomer = customerHooks.useCreate;
export const useUpdateCustomer = customerHooks.useUpdate;
export const useDeleteCustomer = customerHooks.useDelete;
export const useCustomerOptions = customerHooks.useOptions;


const CUSTOMER_STATUS_TERMINATED = 3;


export function useAllocatableCustomerOptions() {
  return useQuery({
    queryKey: [...queryKeys.customers.all, 'options', 'allocatable'],
    queryFn: async (): Promise<SelectOption[]> => {
      const res = await get<PaginatedData<Customer>>('/customers', { per_page: 1000 });
      const items = res.data?.items ?? [];
      return items
        .filter((c) => c.customer_status !== CUSTOMER_STATUS_TERMINATED)
        .map((c) => ({ label: c.customer_name, value: c.id }));
    }
  });
}


export function useCustomerCabinets(id: number) {
  return useQuery({
    queryKey: queryKeys.customers.cabinets(id),
    queryFn: async () => {
      const res = await get<Cabinet[]>(`/customers/${id}/cabinets`);
      return res.data;
    },
    enabled: id > 0
  });
}


export function useCustomerDevices(id: number) {
  return useQuery({
    queryKey: queryKeys.customers.devices(id),
    queryFn: async () => {
      const res = await get<Device[]>(`/customers/${id}/devices`);
      return res.data;
    },
    enabled: id > 0
  });
}


export function useCustomerAssets(id: number) {
  return useQuery({
    queryKey: queryKeys.customers.assets(id),
    queryFn: async () => {
      const res = await get<CustomerAssets>(`/customers/${id}/assets`);
      return res.data;
    },
    enabled: id > 0
  });
}


export function useCustomerStatistics(id: number) {
  return useQuery({
    queryKey: queryKeys.customers.statistics(id),
    queryFn: async () => {
      const res = await get<Record<string, unknown>>(`/customers/${id}/statistics`);
      return res.data;
    },
    enabled: id > 0
  });
}


export async function exportCustomerAssets(id: number, customerName: string) {
  const res = await apiClient.get(`/customers/${id}/assets-export`, {
    responseType: 'blob'
  });
  const blob = res.data as Blob;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${customerName}_资源统计.xlsx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}


export interface TerminationPreview {
  customer: Customer;
  assets: CustomerAssets;
  will_terminate: boolean;
}


export interface TerminationArchiveMeta {
  id: number;
  created_at: string | null;
  operator_id: number;
  operator_name: string | null;
  pdf_size: number | null;
  reason: string | null;
  has_pdf: boolean;
  summary: Record<string, unknown>;
}


export function useTerminationPreview(id: number) {
  return useQuery({
    queryKey: [...queryKeys.customers.all, 'termination-preview', id],
    queryFn: async () => {
      const res = await get<TerminationPreview>(`/customers/${id}/termination-preview`);
      return res.data;
    },
    enabled: id > 0
  });
}


export function useTerminationArchives(id: number) {
  return useQuery({
    queryKey: [...queryKeys.customers.all, 'termination-archives', id],
    queryFn: async () => {
      const res = await get<TerminationArchiveMeta[]>(`/customers/${id}/termination-archives`);
      return res.data;
    },
    enabled: id > 0
  });
}


export async function downloadTerminationArchive(id: number, customerName: string) {
  const res = await apiClient.get(`/customers/${id}/termination-archive`, {
    responseType: 'blob'
  });
  const blob = res.data as Blob;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${customerName}_终止存档.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}


export interface TerminateCustomerRequest {
  reason?: string;
}


export function useTerminateCustomer() {
  const queryClient = useQueryClient();
  return useMutation<Customer, Error, { id: number; reason?: string }>({
    mutationFn: async ({ id, reason }) => {
      const res = await post<Customer, TerminateCustomerRequest>(
        `/customers/${id}/terminate`,
        reason ? { reason } : {}
      );
      return res.data;
    },
    onSuccess: () => {
      
      queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
    }
  });
}
