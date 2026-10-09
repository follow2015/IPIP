import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';
import { PER_PAGE_CAP } from '@/constants/pagination';
import type { PaginatedData, PaginationParams } from '@/types/api';

export type CarrierType = 'basic' | 'isp' | 'idc' | 'agent';

export type CarrierStatus = 'active' | 'inactive';

export interface Carrier {
  id: number;
  name: string;
  short_name: string | null;
  carrier_type: CarrierType | null;
  status: CarrierStatus | null;
  contact_person: string | null;
  contact_phone: string | null;
  hotline: string | null;
  email: string | null;
  default_sla_level: string | null;
  qualification_no: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface CarrierQueryParams extends PaginationParams {
  status?: string;
  carrier_type?: string;
  keyword?: string;
}

export interface CarrierPayload {
  name?: string;
  short_name?: string | null;
  carrier_type?: CarrierType | null;
  status?: CarrierStatus | null;
  contact_person?: string | null;
  contact_phone?: string | null;
  hotline?: string | null;
  email?: string | null;
  default_sla_level?: string | null;
  qualification_no?: string | null;
  notes?: string | null;
}


export function useCarrierList(params?: CarrierQueryParams) {
  return useQuery({
    queryKey: queryKeys.carriers.list(params ?? {}),
    queryFn: () =>
      get<{ items: Carrier[]; total: number; page: number; per_page: number }>(
        '/carriers',
        params as Record<string, unknown>
      ).then(
        (res) =>
          (res.data ?? { items: [], total: 0, page: 1, per_page: 20 }) as PaginatedData<Carrier>
      )
  });
}

export function useCarrierOptions() {
  return useQuery({
    queryKey: queryKeys.carriers.options,
    queryFn: async () => {
      const res = await get<{ items: Carrier[]; total: number }>('/carriers', {
        status: 'active',
        per_page: PER_PAGE_CAP
      });
      return (res.data?.items ?? []).map((c) => ({ label: c.name, value: c.id }));
    }
  });
}


function useInvalidateCarriers() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.carriers.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.circuits.all });
  };
}

export function useCreateCarrier() {
  const invalidate = useInvalidateCarriers();
  return useMutation({
    mutationFn: (data: CarrierPayload) => post<Carrier>('/carriers', data),
    onSuccess: invalidate
  });
}

export function useUpdateCarrier() {
  const invalidate = useInvalidateCarriers();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CarrierPayload }) =>
      put<Carrier>(`/carriers/${id}`, data),
    onSuccess: invalidate
  });
}

export function useDeleteCarrier() {
  const invalidate = useInvalidateCarriers();
  return useMutation({
    mutationFn: (id: number) => del<null>(`/carriers/${id}`),
    onSuccess: invalidate
  });
}
