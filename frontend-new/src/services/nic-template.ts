/**
 * 网卡模板服务
 * - 获取网卡模板列表（用于快速创建网卡）
 */
import { useQuery } from '@tanstack/react-query';
import { get } from './api-client';

interface NicTemplate {
  id: number;
  name: string;
  port_name: string;
  speed: string;
  description: string | null;
}

export function useNicTemplates() {
  return useQuery({
    queryKey: ['nic-templates'],
    queryFn: async () => {
      const res = await get<NicTemplate[]>('/nic-templates');
      return res.data;
    },
  });
}
