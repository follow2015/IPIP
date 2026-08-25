/**
 * 配件模板服务
 * - CRUD + 按类别查询 + TanStack Query hooks
 * 对齐后端 /api/component-templates 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';

export interface ComponentTemplate {
  id: number;
  category: 'cpu' | 'memory' | 'disk' | 'nic' | 'gpu';
  customer_id: number | null;
  customer_name: string | null;
  brand: string;
  model: string;
  spec: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
  remark: string;
  created_at: string;
  updated_at: string;
}

async function fetchTemplates(category?: string, customerId?: number | null, includeGlobal = true) {
  const params: Record<string, string | number> = { is_active: 'true' };
  if (category) params.category = category;
  if (customerId) params.customer_id = customerId;
  if (customerId && !includeGlobal) params.include_global = 'false';
  const res = await get<ComponentTemplate[]>('/component-templates', params);
  return res.data ?? [];
}

export function useComponentTemplates(category?: string, customerId?: number | null, includeGlobal = true) {
  return useQuery({
    queryKey: [...(queryKeys.devices.all ?? ['devices']), 'component-templates', category, customerId, includeGlobal],
    queryFn: () => fetchTemplates(category, customerId, includeGlobal),
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<ComponentTemplate>) => post<ComponentTemplate>('/component-templates', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices', 'component-templates'] });
    },
  });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ComponentTemplate> }) =>
      put<ComponentTemplate>(`/component-templates/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices', 'component-templates'] });
    },
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del<void>(`/component-templates/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices', 'component-templates'] });
    },
  });
}
