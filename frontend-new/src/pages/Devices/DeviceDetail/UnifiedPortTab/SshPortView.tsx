/**
 * SshPortView — 网管（SSH）模式的端口区块
 * 工具栏（筛选 + 同步）+ 端口可视化面板 + 批量操作 + 端口列表
 */
import { useMemo, useCallback } from 'react';
import { Button, Space, Switch, Tooltip } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import type { TableProps } from 'antd';
import FilterBar from '@/components/FilterBar';
import SwitchPortPanel from '@/components/SwitchPortPanel';
import type { SwitchPort } from '@/types/models';
import type { SubmitActionFn, RenderPortActionsFn, RenderBatchActionsFn } from '@/types/port';
import { useTable } from '@/hooks/useTable';
import { useDevicePortSyncEnabled, useSetDevicePortSyncEnabled } from '@/services/network-port';
import { useDeviceMonitorStatus } from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { buildSshColumns } from './columns';
import { PortTable } from './PortTable';
import { PortStats } from './PortStats';
import { USAGE_STATUS_FILTER_OPTIONS } from './constants';

interface SshPortViewProps {
  deviceId: number;
  sortedPorts: SwitchPort[];
  filteredPorts: SwitchPort[];
  portStats: Record<string, number>;
  filterTable: ReturnType<typeof useTable>;
  isLoading: boolean;
  refetch: () => void;
  handleSync: () => void;
  isPending: boolean;
  submitAction: SubmitActionFn;
  renderPortActions?: RenderPortActionsFn;
  renderBatchActions?: RenderBatchActionsFn;
  selectedRowKeys: React.Key[];
  rowSelection: TableProps<SwitchPort>['rowSelection'];
  highlightPort: string | null;
  onPortPanelClick: (port: SwitchPort) => void;
  onClearSelection: () => void;
}

export function SshPortView({
  deviceId,
  sortedPorts,
  filteredPorts,
  portStats,
  filterTable,
  isLoading,
  refetch,
  handleSync,
  isPending,
  submitAction,
  renderPortActions,
  renderBatchActions,
  selectedRowKeys,
  rowSelection,
  highlightPort,
  onPortPanelClick,
  onClearSelection
}: SshPortViewProps) {
  const columns = useMemo(
    () =>
      buildSshColumns({
        deviceId,
        renderPortActions: renderPortActions ?? (() => null),
        refetch,
        submitAction
      }),
    [deviceId, renderPortActions, refetch, submitAction]
  );

  const message = useMessage();
  const portSyncQuery = useDevicePortSyncEnabled(deviceId);
  const setPortSync = useSetDevicePortSyncEnabled(deviceId);
  const deviceMonitorStatus = useDeviceMonitorStatus(deviceId);
  const configuredProtocols = deviceMonitorStatus.data?.configured_protocols ?? [];
  const hasMonitorCredential =
    configuredProtocols.includes('snmp') || configuredProtocols.includes('zabbix');
  const effectiveEnabled = portSyncQuery.data?.effective_enabled ?? false;
  const globalEnabled = portSyncQuery.data?.global_enabled ?? false;
  const deviceOverride = portSyncQuery.data?.port_sync_enabled ?? null;

  const handleTogglePortSync = useCallback(
    (checked: boolean) => {
      setPortSync.mutate(checked, {
        onSuccess: () => {
          message.success(checked ? '已开启端口状态自动同步' : '已关闭端口状态自动同步');
        },
        onError: () => {
          message.error('开关设置失败');
        }
      });
    },
    [setPortSync, message]
  );

  const handleResetToGlobal = useCallback(() => {
    setPortSync.mutate(null, {
      onSuccess: () => {
        message.success('已重置为跟随全局开关');
      },
      onError: () => {
        message.error('重置失败');
      }
    });
  }, [setPortSync, message]);

  return (
    <>
      {/* 工具栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12
        }}
      >
        <FilterBar
          filters={[
            {
              key: 'usage_status',
              label: '占用状态筛选',
              type: 'select',
              options: USAGE_STATUS_FILTER_OPTIONS,
              width: 160
            }
          ]}
          table={filterTable}
          prefix={<PortStats portStats={portStats} />}
        />
        <Space>
          <Tooltip
            title={
              !hasMonitorCredential
                ? '请先添加 SNMP 或 Zabbix 监控凭据后才能开启端口状态自动同步'
                : deviceOverride === null
                  ? `跟随全局开关（当前：${globalEnabled ? '开' : '关'}），点击切换为设备级强制开关。开启后监控轮询时用 SNMP/Zabbix 凭据更新端口状态，SSH 同步仍保留全量替换`
                  : '设备级开关已强制设置，开启后监控轮询时仅更新端口状态，SSH 同步仍保留全量替换。点击"跟随全局"可恢复'
            }
          >
            <span>
              <Switch
                checked={effectiveEnabled}
                onChange={handleTogglePortSync}
                disabled={!hasMonitorCredential || setPortSync.isPending}
                checkedChildren="状态同步"
                unCheckedChildren="不同步"
                size="small"
              />
            </span>
          </Tooltip>
          {deviceOverride !== null && (
            <Button
              size="small"
              type="link"
              onClick={handleResetToGlobal}
              disabled={setPortSync.isPending}
            >
              跟随全局
            </Button>
          )}
          <Button icon={<SyncOutlined />} onClick={handleSync} loading={isPending}>
            同步数据
          </Button>
        </Space>
      </div>

      {/* 端口可视化面板 */}
      <SwitchPortPanel ports={sortedPorts} onPortClick={onPortPanelClick} />

      {/* 批量操作工具栏（图形化面板下方）— 由注入渲染器提供，避免 Devices→Switches 耦合 */}
      {renderBatchActions?.({
        selectedPorts: selectedRowKeys as string[],
        onClearSelection,
        hasSsh: true,
        refetch
      })}

      {/* 端口列表 */}
      <PortTable
        columns={columns}
        dataSource={filteredPorts}
        loading={isLoading}
        rowSelection={rowSelection}
        highlightPort={highlightPort}
      />
    </>
  );
}
