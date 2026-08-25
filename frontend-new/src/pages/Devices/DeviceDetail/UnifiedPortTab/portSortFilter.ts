/**
 * 端口纯逻辑：排序 / 统计 / 筛选 / 回退轮询
 * 零渲染依赖，优先下沉（拆分护栏：纯逻辑层）
 */
import type { SwitchPort } from '@/types/models';
import { classifyPortType, extractPortIndex, PORT_TYPE_SORT_WEIGHT } from '@/utils/portType';


export function comparePorts(a: SwitchPort, b: SwitchPort): number {
  const typeA = classifyPortType(a.port_name);
  const typeB = classifyPortType(b.port_name);
  const weightA = PORT_TYPE_SORT_WEIGHT[typeA] ?? 300;
  const weightB = PORT_TYPE_SORT_WEIGHT[typeB] ?? 300;
  if (weightA !== weightB) return weightA - weightB;
  return extractPortIndex(a.port_name) - extractPortIndex(b.port_name);
}


export function computePortStats(ports: SwitchPort[]): Record<string, number> {
  return ports.reduce(
    (acc, p) => {
      const key = p.usage_status ?? 'unknown';
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}


export function filterPortsByStatus(ports: SwitchPort[], status?: string): SwitchPort[] {
  if (!status) return ports;
  return ports.filter((p) => p.usage_status === status);
}


export function startPolling(
  callback: () => void,
  intervalMs: number,
  maxCount: number
): () => void {
  let count = 0;
  const timer = setInterval(() => {
    callback();
    if (++count >= maxCount) clearInterval(timer);
  }, intervalMs);
  return () => clearInterval(timer);
}
