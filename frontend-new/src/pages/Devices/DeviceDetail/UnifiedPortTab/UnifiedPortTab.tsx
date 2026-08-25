/**
 * UnifiedPortTab — 统一端口标签页（组合根）
 *
 * 根据 hasSsh 自动切换能力：
 * - hasSsh=true  → 端口可视化面板 + 完整端口列表 + 全套操作(PortActions) + SSE + 同步/刷新
 * - hasSsh=false → 端口列表 + 手动 CRUD + 简化操作(启用/禁用/编辑/删除)
 *
 * 本文件仅做组合：数据源选择 + 排序/筛选/统计 + 共享选择态/高亮 + 分支渲染。
 * 业务逻辑下沉至 usePortSync / PortManualCrud，展示下沉至 SshPortView / 各 Modal。
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import type { TableProps } from 'antd';
import { useSwitchWithPorts } from '@/services/switch';
import { useNetworkPorts } from '@/services/network-port';
import { useDeviceMonitorStatus } from '@/services/monitor';
import { useTable } from '@/hooks/useTable';
import type { SwitchPort } from '@/types/models';
import type { RenderPortActionsFn, RenderBatchActionsFn } from '@/types/port';
import { usePortSortFilter } from './usePortSortFilter';
import { usePortSync } from './usePortSync';
import { SshPortView } from './SshPortView';
import { PortManualCrud } from './PortManualCrud';

interface UnifiedPortTabProps {
  deviceId: number;
  hasSsh: boolean;
  renderPortActions?: RenderPortActionsFn;
  renderBatchActions?: RenderBatchActionsFn;
}

function UnifiedPortTab({
  deviceId,
  hasSsh,
  renderPortActions,
  renderBatchActions
}: UnifiedPortTabProps) {
  const switchWithPorts = useSwitchWithPorts(deviceId, { enabled: hasSsh });
  const networkPorts = useNetworkPorts(deviceId, { enabled: !hasSsh });
  const deviceMonitorStatus = useDeviceMonitorStatus(deviceId);
  const configuredProtocols = deviceMonitorStatus.data?.configured_protocols ?? [];
  const hasAutoPortCredential =
    !hasSsh && (configuredProtocols.includes('snmp') || configuredProtocols.includes('zabbix'));

  const rawPorts: SwitchPort[] = hasSsh
    ? (switchWithPorts.data?.ports ?? [])
    : (networkPorts.data ?? []);
  const isLoading = hasSsh ? switchWithPorts.isLoading : networkPorts.isLoading;
  const refetch = hasSsh ? switchWithPorts.refetch : networkPorts.refetch;

  const filterTable = useTable();
  const { sortedPorts, filteredPorts, portStats } = usePortSortFilter(rawPorts, filterTable);

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const rowSelection: TableProps<SwitchPort>['rowSelection'] = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
    preserveSelectedRowKeys: true
  };

  const [highlightPort, setHighlightPort] = useState<string | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const scheduleClearHighlight = useCallback(() => {
    clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => setHighlightPort(null), 3000);
  }, []);
  const handlePortPanelClick = useCallback(
    (port: SwitchPort) => {
      setHighlightPort(port.port_name);
      scheduleClearHighlight();
    },
    [scheduleClearHighlight]
  );
  useEffect(() => () => clearTimeout(highlightTimerRef.current), []);

  const { handleSync, isPending, submitAction } = usePortSync({
    deviceId,
    refetch,
    setHighlightPort,
    scheduleClearHighlight,
    hasSsh
  });

  return (
    <div>
      {hasSsh ? (
        <SshPortView
          deviceId={deviceId}
          sortedPorts={sortedPorts}
          filteredPorts={filteredPorts}
          portStats={portStats}
          filterTable={filterTable}
          isLoading={isLoading}
          refetch={refetch}
          handleSync={handleSync}
          isPending={isPending}
          submitAction={submitAction}
          renderPortActions={renderPortActions}
          renderBatchActions={renderBatchActions}
          selectedRowKeys={selectedRowKeys}
          rowSelection={rowSelection}
          highlightPort={highlightPort}
          onPortPanelClick={handlePortPanelClick}
          onClearSelection={() => setSelectedRowKeys([])}
        />
      ) : (
        <PortManualCrud
          deviceId={deviceId}
          sortedPorts={sortedPorts}
          filteredPorts={filteredPorts}
          portStats={portStats}
          filterTable={filterTable}
          isLoading={isLoading}
          refetch={refetch}
          renderBatchActions={renderBatchActions}
          selectedRowKeys={selectedRowKeys}
          rowSelection={rowSelection}
          highlightPort={highlightPort}
          onClearSelection={() => setSelectedRowKeys([])}
          hasSnmpCredential={hasAutoPortCredential}
        />
      )}
    </div>
  );
}

export default UnifiedPortTab;
