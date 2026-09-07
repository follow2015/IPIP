import { useQuery } from '@tanstack/react-query';
import { get } from './api-client';
import { queryKeys } from './query-keys';
import type { PaginatedData, PaginationParams } from '@/types/api';

export interface IPAuditLog {
  id: string;
  source: 'allocation' | 'ban';
  ip_address: string;
  room_id: number | null;
  action: string;
  operator_id: number | null;
  customer_id: number | null;
  customer_name: string | null;
  ban_mode: string | null;
  switch_id: number | null;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface IPAuditLogParams extends PaginationParams {
  action?: string;
  ip_address?: string;
  room_id?: number;
  operator_id?: number;
  start_time?: string;
  end_time?: string;
}

export function useIPAuditLogs(params?: IPAuditLogParams) {
  return useQuery({
    queryKey: queryKeys.ipAudit.list(params),
    queryFn: async () => {
      const res = await get<PaginatedData<IPAuditLog>>(
        '/ip-audit/logs',
        params as Record<string, unknown>
      );
      return res.data;
    }
  });
}
