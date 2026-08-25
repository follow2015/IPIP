/**
 * IP 分配日志服务
 * - 查询指定 IP 地址的分配历史
 * 对齐后端 /api/ip/<address>/allocation-logs 端点
 */
import { useQuery } from '@tanstack/react-query';
import { get } from './api-client';
import { queryKeys } from './query-keys';
import type { IPAllocationLog } from '@/types/models';


export function useIPAllocationLogs(ipAddress: string, roomId?: number) {
  return useQuery({
    queryKey: [...queryKeys.ip.detail(ipAddress), 'allocation-logs', roomId],
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (roomId) params.room_id = roomId;
      const res = await get<IPAllocationLog[]>(`/ip/${ipAddress}/allocation-logs`, params);
      return res.data;
    },
    enabled: !!ipAddress,
  });
}
