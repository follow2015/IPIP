
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, del, patch, put } from '../api-client';
import { createCrudHooks } from '../crud-factory';
import { queryKeys } from '../query-keys';

import type { components } from '@/types/api-generated';

const metricTemplateHooks = createCrudHooks<
  MetricTemplateItem,
  MetricTemplateUpsert,
  MetricTemplateUpsert & { id: number }
>({
  basePath: '/monitor/metric-templates',
  queryKey: queryKeys.monitor.metricTemplatesCrud
});

export const useMetricTemplates = metricTemplateHooks.useList;

export function useUpsertMetricTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: MetricTemplateUpsert) => {
      const res = await put<{ id: number }>(`/monitor/metric-templates`, payload);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateOidAudit });
    }
  });
}

export type MetricTemplateList = components['schemas']['MetricTemplateListResponse'];

export type MetricTemplateItem = components['schemas']['MetricTemplateItem'];

export type MetricTemplateOidAudit = components['schemas']['MetricTemplateOidAuditResponse'];

export type MetricTemplateOidAuditItem = components['schemas']['MetricTemplateOidAuditItem'];

export function useMetricTemplateOidAudit(enabled = true) {
  return useQuery({
    queryKey: queryKeys.monitor.metricTemplateOidAudit,
    queryFn: async () => {
      const res = await get<MetricTemplateOidAudit>('/monitor/metric-templates/oid-audit');
      return res.data;
    },
    enabled
  });
}

export interface MetricTemplateUpsert {
  device_type: string;
  metric_key: string;
  category?: string | null;
  display_name?: string | null;
  source?: string;
  vendor?: string | null;
  mib?: string | null;
  oid_symbol?: string | null;
  oid?: string | null;
  zabbix_item_key?: string | null;
  index_kind?: string | null;
  metric_type?: string;
  unit?: string | null;
  poll_interval?: number;
  threshold?: Record<string, unknown> | null;
  severity_default?: string | null;
  enabled?: boolean;
  description?: string | null;
  runbook_url?: string | null;
  runbook_title?: string | null;
}

export interface MetricTemplateGroupItem {
  id: number;
  name: string;
  device_type: string;
  source: string;
  vendor: string | null;
  display_order: number;
  enabled: boolean;
  description: string | null;
  template_count?: number;
}

export interface MetricTemplateGroupDetail extends MetricTemplateGroupItem {
  templates: MetricTemplateItem[];
}

export interface MetricTemplateGroupUpsert {
  name: string;
  device_type: string;
  source: string;
  vendor?: string | null;
  display_order?: number;
  enabled?: boolean;
  description?: string | null;
}

export function useMetricTemplateGroups() {
  return useQuery({
    queryKey: queryKeys.monitor.metricTemplateGroups,
    queryFn: async () => {
      const res = await get<MetricTemplateGroupItem[]>('/monitor/metric-template-groups');
      return res.data;
    }
  });
}

export function useMetricTemplateGroupDetail(groupId: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.monitor.metricTemplateGroup(groupId),
    queryFn: async () => {
      const res = await get<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}`
      );
      return res.data;
    },
    enabled: enabled && groupId > 0
  });
}

export function useCreateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: MetricTemplateGroupUpsert) => {
      const res = await post<MetricTemplateGroupItem>('/monitor/metric-template-groups', payload);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups })
  });
}

export function useUpdateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number } & Partial<MetricTemplateGroupUpsert>) => {
      const res = await put<MetricTemplateGroupItem>(
        `/monitor/metric-template-groups/${id}`,
        payload
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useDeleteMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await del<{ id: number }>(`/monitor/metric-template-groups/${id}`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useAddTemplatesToGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, templateIds }: { groupId: number; templateIds: number[] }) => {
      const res = await post<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}/items`,
        { template_ids: templateIds }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useRemoveTemplateFromGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, templateId }: { groupId: number; templateId: number }) => {
      const res = await del<MetricTemplateGroupDetail>(
        `/monitor/metric-template-groups/${groupId}/items/${templateId}`
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplateGroups });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchUpdateMetricTemplateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      deviceIds,
      metricTemplateGroupId
    }: {
      deviceIds: number[];
      metricTemplateGroupId: number | null;
    }) => {
      const res = await post<{ updated: number; skipped: number }>(
        '/devices/batch-metric-template-group',
        { device_ids: deviceIds, metric_template_group_id: metricTemplateGroupId }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchUpdatePortSyncEnabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      deviceIds,
      portSyncEnabled
    }: {
      deviceIds: number[];
      portSyncEnabled: boolean | null;
    }) => {
      const res = await post<{
        updated: number;
        with_credential: number;
        without_credential: number;
        non_network: number;
        skipped: number;
      }>('/devices/batch-port-sync-enabled', {
        device_ids: deviceIds,
        port_sync_enabled: portSyncEnabled
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] });
    }
  });
}

export const useDeleteMetricTemplate = metricTemplateHooks.useDelete;

export function useBatchDeleteMetricTemplates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await del<{ deleted: number; total: number }>('/monitor/metric-templates/batch', {
        ids
      });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}

export function useBatchToggleMetricTemplateEnabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { ids: number[]; enabled: boolean }) => {
      const res = await patch<{ updated: number; total: number; enabled: boolean }>(
        '/monitor/metric-templates/batch-enabled',
        params
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.metricTemplatesCrud })
  });
}
