import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put, post, del } from './api-client';
import { queryKeys } from './query-keys';
import type { PaginatedData, PaginationParams } from '@/types/api';

export type BillingMode = 'flat' | 'commit_95' | 'commit_peak' | 'commit_avg' | 'per_gb';

export type CircuitStatus = 'pending' | 'active' | 'fault' | 'suspended' | 'terminated';

export interface Circuit {
  id: number;
  circuit_no: string;
  name: string | null;
  carrier_id: number | null;
  carrier_name?: string | null;
  customer_id: number | null;
  customer_name?: string | null;

  billing_mode: BillingMode | null;
  bandwidth_mbps: number | null;
  bandwidth_step: number | null;
  bandwidth_display?: string | null;
  committed_mbps: number | null;
  committed_is_derived?: boolean;
  monthly_fee: number | null;
  overage_unit_price: number | null;
  traffic_unit_price: number | null;
  currency: string | null;

  access_type: string | null;
  status: CircuitStatus | null;
  sla_level: string | null;
  start_date: string | null;
  end_date: string | null;
  contract_no: string | null;

  a_end_room_id: number | null;
  z_end_room_id: number | null;
  a_end_device_id: number | null;
  z_end_device_id: number | null;
  a_end_port_id: number | null;
  z_end_port_id: number | null;
  a_end_desc: string | null;
  z_end_desc: string | null;
  notes: string | null;

  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface CircuitSegment {
  id: number;
  circuit_id: number;
  seq: number;
  connection_id: number | null;
  anchor_lost: boolean;
  device_id: number | null;
  port_id: number | null;
  device_name?: string | null;
  port_name?: string | null;
  device_missing?: boolean;
  port_missing?: boolean;
  hop_desc: string | null;
  notes: string | null;
}

export interface CircuitDetail extends Circuit {
  segments: CircuitSegment[];
}

export interface CircuitImpact {
  connection_id?: number;
  shared_by?: number;
  items: Circuit[];
  customer_ids?: number[];
  total: number;
}

export interface CircuitQueryParams extends PaginationParams {
  status?: string;
  billing_mode?: string;
  carrier_id?: number;
  customer_id?: number;
  room_id?: number;
  expiring_in_days?: number;
  keyword?: string;
}

export interface CircuitPayload {
  circuit_no?: string;
  name?: string | null;
  carrier_id?: number | null;
  customer_id?: number | null;

  billing_mode?: BillingMode | null;
  bandwidth_value?: number | null;
  bandwidth_unit?: 'M' | 'G' | 'T' | 'P' | null;
  bandwidth_mbps?: number | null;
  bandwidth_step?: number | null;
  committed_value?: number | null;
  committed_unit?: 'M' | 'G' | 'T' | 'P' | null;
  committed_mbps?: number | null;
  monthly_fee?: number | null;
  overage_unit_price?: number | null;
  traffic_unit_price?: number | null;
  currency?: string | null;

  access_type?: string | null;
  status?: CircuitStatus | null;
  sla_level?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  contract_no?: string | null;

  a_end_room_id?: number | null;
  z_end_room_id?: number | null;
  a_end_device_id?: number | null;
  z_end_device_id?: number | null;
  a_end_port_id?: number | null;
  z_end_port_id?: number | null;
  a_end_desc?: string | null;
  z_end_desc?: string | null;
  notes?: string | null;
}


export function useCircuitList(params?: CircuitQueryParams) {
  return useQuery({
    queryKey: queryKeys.circuits.list(params ?? {}),
    queryFn: () =>
      get<{ items: Circuit[]; total: number; page: number; per_page: number }>(
        '/circuits',
        params as Record<string, unknown>
      ).then(
        (res) =>
          (res.data ?? { items: [], total: 0, page: 1, per_page: 20 }) as PaginatedData<Circuit>
      )
  });
}

export function useCircuitDetail(id: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.circuits.detail(id as number),
    enabled: !!id,
    queryFn: () => get<CircuitDetail>(`/circuits/${id}`).then((res) => res.data as CircuitDetail)
  });
}

export function useCircuitSegments(id: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.circuits.segments(id as number),
    enabled: !!id,
    queryFn: () =>
      get<{ items: CircuitSegment[]; total: number }>(`/circuits/${id}/segments`).then(
        (res) => res.data?.items ?? []
      )
  });
}

export function useExpiringCircuits(withinDays = 30) {
  return useQuery({
    queryKey: queryKeys.circuits.expiring(withinDays),
    queryFn: () =>
      get<{ items: Circuit[]; total: number }>('/circuits/expiring', {
        within_days: withinDays
      }).then((res) => res.data?.items ?? [])
  });
}

export interface CircuitDevice {
  id: number;
  device_name: string | null;
  hostname: string | null;
}

export function useCircuitDevices(id: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.circuits.devices(id as number),
    enabled: !!id,
    queryFn: () =>
      get<{ items: CircuitDevice[]; total: number }>(`/circuits/${id}/devices`).then(
        (res) => res.data?.items ?? []
      )
  });
}

export function useCircuitImpactByConnection(connectionId: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.circuits.impactByConnection(connectionId as number),
    enabled: !!connectionId,
    queryFn: () =>
      get<CircuitImpact>('/circuits/impact', { connection_id: connectionId }).then(
        (res) => res.data as CircuitImpact
      )
  });
}

export function useCircuitImpactByCustomer(customerId: number | null | undefined) {
  return useQuery({
    queryKey: queryKeys.circuits.impactByCustomer(customerId as number),
    enabled: !!customerId,
    queryFn: () =>
      get<CircuitImpact>('/circuits/impact', { customer_id: customerId }).then(
        (res) => res.data as CircuitImpact
      )
  });
}


function useInvalidateCircuits() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.circuits.all });
    queryClient.invalidateQueries({ queryKey: ['customers'] });
  };
}

export function useCreateCircuit() {
  const invalidate = useInvalidateCircuits();
  return useMutation({
    mutationFn: (data: CircuitPayload) => post<Circuit>('/circuits', data),
    onSuccess: invalidate
  });
}

export function useUpdateCircuit() {
  const invalidate = useInvalidateCircuits();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CircuitPayload }) =>
      put<Circuit>(`/circuits/${id}`, data),
    onSuccess: invalidate
  });
}

export function useDeleteCircuit() {
  const invalidate = useInvalidateCircuits();
  return useMutation({
    mutationFn: (id: number) => del<null>(`/circuits/${id}`),
    onSuccess: invalidate
  });
}

export function useReplaceCircuitSegments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, segments }: { id: number; segments: Partial<CircuitSegment>[] }) =>
      put<null>(`/circuits/${id}/segments`, { segments }),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.circuits.segments(vars.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.circuits.detail(vars.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.circuits.all });
    }
  });
}
