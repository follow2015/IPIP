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
import { getUsageStatusFilterOptions } from './constants';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const usageStatusOptions = useMemo(() => getUsageStatusFilterOptions(t), [t]);
  const columns = useMemo(
    () =>
      buildSshColumns({
        deviceId,
        renderPortActions: renderPortActions ?? (() => null),
        refetch,
        submitAction,
        t: { d: t, c: tCommon }
      }),
    [deviceId, renderPortActions, refetch, submitAction, t, tCommon]
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
          message.success(
            checked ? t('port.message.statusSyncEnabled') : t('port.message.statusSyncDisabled')
          );
        },
        onError: () => {
          message.error(t('port.message.toggleFailed'));
        }
      });
    },
    [setPortSync, message, t]
  );

  const handleResetToGlobal = useCallback(() => {
    setPortSync.mutate(null, {
      onSuccess: () => {
        message.success(t('port.message.resetToGlobal'));
      },
      onError: () => {
        message.error(t('asset.message.resetFailed'));
      }
    });
  }, [setPortSync, message, t]);

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
              label: t('port.filter.usageStatus'),
              type: 'select',
              options: usageStatusOptions,
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
                ? t('port.tooltip.needCredentialStatus')
                : deviceOverride === null
                  ? t('port.tooltip.followGlobalStatus', {
                      state: globalEnabled ? t('port.state.on') : t('port.state.off')
                    })
                  : t('port.tooltip.deviceOverrideStatus', {
                      follow: t('batchMonitor.modeFollow')
                    })
            }
          >
            <span>
              <Switch
                checked={effectiveEnabled}
                onChange={handleTogglePortSync}
                disabled={!hasMonitorCredential || setPortSync.isPending}
                checkedChildren={t('port.switch.statusSync')}
                unCheckedChildren={t('port.switch.notSync')}
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
              {t('batchMonitor.modeFollow')}
            </Button>
          )}
          <Button icon={<SyncOutlined />} onClick={handleSync} loading={isPending}>
            {t('port.action.syncData')}
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
