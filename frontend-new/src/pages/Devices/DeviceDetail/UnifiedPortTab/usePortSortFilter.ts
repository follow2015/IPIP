/**
 * usePortSortFilter — 端口排序 + 筛选 + 统计
 * 承接原组件顶部的 sortedPorts / filteredPorts / portStats 三个 useMemo
 */
import { useMemo } from 'react';
import type { SwitchPort } from '@/types/models';
import { comparePorts, computePortStats, filterPortsByStatus } from './portSortFilter';

interface FilterState {
  filters: { usage_status?: string };
}

export function usePortSortFilter(rawPorts: SwitchPort[], filterTable: FilterState) {
  const sortedPorts = useMemo(() => [...rawPorts].sort(comparePorts), [rawPorts]);

  const filteredPorts = useMemo(
    () => filterPortsByStatus(sortedPorts, filterTable.filters.usage_status),
    [sortedPorts, filterTable.filters.usage_status]
  );

  const portStats = useMemo(() => computePortStats(rawPorts), [rawPorts]);

  return { sortedPorts, filteredPorts, portStats };
}
