
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, del, patch, put } from '../api-client';
import apiClient from '../api-client';
import { createCrudHooks } from '../crud-factory';
import { queryKeys } from '../query-keys';

import type { ApiResponse, PaginationParams } from '@/types/api';
import type { components } from '@/types/api-generated';

export interface MibScanResult {
  device_ip: string;
  vendor_id?: string | null;
  oid_count: number;
  type_summary: Record<string, number>;
  detected: MibScanOid[];
  hint: string;
}

export interface MibScanOid {
  oid: string;
  type: string;
  value: string;
  category?: string | null;
  category_label?: string | null;
  category_source?: 'rule' | 'heuristic' | null;
}

export interface MibImportItem {
  oid: string;
  metric_key: string;
  device_type: string;
  category?: string | null;
  display_name?: string | null;
  vendor?: string | null;
  oid_symbol?: string | null;
  metric_type?: string;
  unit?: string;
  severity_default?: string | null;
  description?: string;
}

export function useMibScan() {
  return useMutation({
    mutationFn: async (params: { device_id: number; timeout?: number }) => {
      const res = await apiClient.post<ApiResponse<MibScanResult>>(
        '/monitor/mib-scan',
        params as unknown as Record<string, unknown>,
        { timeout: 120_000 }
      );
      return res.data.data;
    }
  });
}

export function useImportOids() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (items: MibImportItem[]) => {
      const res = await post<{
        imported: { id: number; metric_key: string; oid: string }[];
        count: number;
      }>('/monitor/mib-scan/import', { items });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}


export type OidCategoryRule = Required<components['schemas']['OidCategoryRuleItem']>;

export type DeviceTypeRecommend = Required<components['schemas']['DeviceTypeRecommendItem']>;

const oidCategoryRuleHooks = createCrudHooks<
  OidCategoryRule,
  Omit<OidCategoryRule, 'id'>,
  Partial<OidCategoryRule> & { id: number }
>({
  basePath: '/monitor/oid-category-rules',
  queryKey: queryKeys.monitor.oidCategoryRulesCrud
});

export const useOidCategoryRules = oidCategoryRuleHooks.useList;
export const useCreateOidCategoryRule = oidCategoryRuleHooks.useCreate;
export const useUpdateOidCategoryRule = oidCategoryRuleHooks.useUpdate;
export const useDeleteOidCategoryRule = oidCategoryRuleHooks.useDelete;

export function useDeviceTypeRecommends() {
  return useQuery({
    queryKey: queryKeys.monitor.deviceTypeRecommends,
    queryFn: async () => {
      const res = await get<{ total: number; items: DeviceTypeRecommend[] }>(
        '/monitor/device-type-recommends'
      );
      return res.data;
    }
  });
}

export function useUpdateDeviceTypeRecommend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      device_type,
      categories
    }: {
      device_type: string;
      categories: string[];
    }) => {
      const res = await put<{ device_type: string; categories: string[] }>(
        `/monitor/device-type-recommends/${device_type}`,
        { categories }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.deviceTypeRecommends })
  });
}

export function useRecommendConfig(deviceType: string) {
  return useQuery({
    queryKey: queryKeys.monitor.recommendConfig(deviceType),
    queryFn: async () => {
      const res = await get<{ device_type: string; categories: string[] }>(
        `/monitor/mib-scan/recommend-config?device_type=${deviceType}`
      );
      return res.data.categories;
    }
  });
}

export function usePersistHeuristicRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { oid: string; device_type: string; vendor_id?: string | null }) => {
      const res = await post<{ id: number }>('/monitor/mib-scan/persist-rule', params);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.oidCategoryRulesCrud })
  });
}

export type VendorBrand = Required<components['schemas']['VendorBrandItem']>;

export interface VendorBrandQueryParams extends PaginationParams {
  device_type?: string;
}

const vendorBrandHooks = createCrudHooks<
  VendorBrand,
  Omit<VendorBrand, 'id'>,
  Partial<VendorBrand> & { id: number },
  VendorBrandQueryParams
>({
  basePath: '/monitor/vendor-brands',
  queryKey: queryKeys.monitor.vendorBrandsCrud
});

export const useVendorBrands = vendorBrandHooks.useList;

export function useCreateVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (brand: Omit<VendorBrand, 'id'>) => {
      const res = await post<{ id: number }>('/monitor/vendor-brands', brand);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}

export function useUpdateVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...rest }: Partial<VendorBrand> & { id: number }) => {
      const res = await patch<{ id: number }>(
        `/monitor/vendor-brands/${id}`,
        rest as Record<string, unknown>
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}

export function useDeleteVendorBrand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await del<{ id: number }>(`/monitor/vendor-brands/${id}`);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.vendorBrandsCrud })
  });
}
