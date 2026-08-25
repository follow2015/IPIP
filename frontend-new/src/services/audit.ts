/**
 * 审计日志服务
 * - 查询审计日志列表，支持 action/resource/operator 过滤
 * 对齐后端 /api/audit/logs 端点
 */
import { useQuery } from '@tanstack/react-query';
import { get } from './api-client';
import { queryKeys } from './query-keys';
import type { AuditLog } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';
import type { AuditLogQuery } from '@/types/api-bridge';


export type AuditLogQueryParams = Partial<AuditLogQuery> & PaginationParams;


export function useAuditLogs(params?: AuditLogQueryParams) {
  return useQuery({
    queryKey: queryKeys.auditLogs.list(params),
    queryFn: async () => {
      const res = await get<PaginatedData<AuditLog>>('/audit/logs', params as Record<string, unknown>);
      return res.data;
    },
  });
}
