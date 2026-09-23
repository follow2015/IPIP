/**
 * PortManualCrud — 非网管（手动 CRUD）模式的端口区块
 * 工具栏（筛选 + 新增）+ 批量操作 + 端口列表 + 新增/编辑弹窗 + 增删改/批量 handler
 */
import { useCallback, useMemo, useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import type { TableProps } from 'antd';
import { Button, Alert, Switch, Tooltip, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import FilterBar from '@/components/FilterBar';
import type { SwitchPort } from '@/types/models';
import type { RenderBatchActionsFn } from '@/types/port';
import { useTable } from '@/hooks/useTable';
import {
  useDeleteNetworkPort,
  useUpdateNetworkPort,
  useUpdatePortUsageStatus,
  useDevicePortSyncEnabled,
  useSetDevicePortSyncEnabled
} from '@/services/network-port';
import { useMessage } from '@/hooks/useMessage';
import { useConfirm } from '@/utils/confirm';
import { useTranslation } from 'react-i18next';
import { buildManualColumns } from './columns';
import { PortTable } from './PortTable';
import { PortStats } from './PortStats';
import { PortBatchAddModal } from './PortBatchAddModal';
import { PortEditModal } from './PortEditModal';
import { getUsageStatusFilterOptions } from './constants';

interface PortManualCrudProps {
  deviceId: number;
  sortedPorts: SwitchPort[];
  filteredPorts: SwitchPort[];
  portStats: Record<string, number>;
  filterTable: ReturnType<typeof useTable>;
  isLoading: boolean;
  refetch: () => void;
  selectedRowKeys: React.Key[];
  rowSelection: TableProps<SwitchPort>['rowSelection'];
  highlightPort: string | null;
  onClearSelection: () => void;
  renderBatchActions?: RenderBatchActionsFn;
  hasSnmpCredential?: boolean;
}

export function PortManualCrud({
  deviceId,
  sortedPorts,
  filteredPorts,
  portStats,
  filterTable,
  isLoading,
  refetch,
  selectedRowKeys,
  rowSelection,
  highlightPort,
  onClearSelection,
  renderBatchActions,
  hasSnmpCredential = false
}: PortManualCrudProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const message = useMessage();
  const addModal = useDisclosure();
  const editModal = useDisclosure();
  const [editingPort, setEditingPort] = useState<SwitchPort | null>(null);

  const updatePort = useUpdateNetworkPort(deviceId);
  const deletePort = useDeleteNetworkPort(deviceId);
  const updateUsageStatus = useUpdatePortUsageStatus(deviceId);

  const portSyncQuery = useDevicePortSyncEnabled(deviceId);
  const setPortSync = useSetDevicePortSyncEnabled(deviceId);
  const effectiveEnabled = portSyncQuery.data?.effective_enabled ?? false;
  const globalEnabled = portSyncQuery.data?.global_enabled ?? false;
  const deviceOverride = portSyncQuery.data?.port_sync_enabled ?? null;

  const handleTogglePortSync = useCallback(
    (checked: boolean) => {
      setPortSync.mutate(checked, {
        onSuccess: () => {
          message.success(
            checked ? t('port.message.syncEnabled') : t('port.message.syncDisabled')
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

  const handleEdit = useCallback((port: SwitchPort) => {
    setEditingPort(port);
    editModal.open();
  }, []);

  const handleDelete = useCallback(
    (port: SwitchPort) => {
      confirm({
        title: t('port.confirm.deleteTitle'),
        content: t('port.confirm.deleteContent', { name: port.port_name }),
        okButtonProps: { danger: true },
        onOk: async () => {
          await deletePort.mutateAsync(port.id);
          message.success(t('port.message.deleted'));
        }
      });
    },
    [confirm, deletePort, message, t]
  );

  const handleToggleUsageStatus = useCallback(
    (port: SwitchPort) => {
      const disabling = port.usage_status !== 'disabled';
      confirm({
        title: disabling ? t('port.confirm.disableTitle') : t('port.confirm.enableTitle'),
        content: disabling
          ? t('port.confirm.disableContent', { name: port.port_name })
          : t('port.confirm.enableContent', { name: port.port_name }),
        onOk: async () => {
          await updateUsageStatus.mutateAsync({
            portId: port.id,
            usageStatus: disabling ? 'disabled' : 'free'
          });
          message.success(disabling ? t('port.message.disabled') : t('port.message.enabled'));
        }
      });
    },
    [confirm, updateUsageStatus, message, t]
  );

  const handleBatchLocalUpdate = useCallback(
    async (portNames: string[], updates: Record<string, unknown>) => {
      const portsToUpdate = sortedPorts.filter((p) => portNames.includes(p.port_name));
      const results = await Promise.allSettled(
        portsToUpdate.map((port) => updatePort.mutateAsync({ portId: port.id, data: updates }))
      );
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed > 0) {
        message.warning(t('port.message.batchUpdatePartialFailed', { count: failed }));
      } else {
        message.success(t('port.message.batchUpdated', { count: portsToUpdate.length }));
      }
    },
    [sortedPorts, updatePort, message, t]
  );

  const usageStatusOptions = useMemo(() => getUsageStatusFilterOptions(t), [t]);

  const columns = useMemo(
    () =>
      buildManualColumns({
        onToggleUsageStatus: handleToggleUsageStatus,
        onEdit: handleEdit,
        onDelete: handleDelete,
        t: { d: t, c: tCommon }
      }),
    [handleToggleUsageStatus, handleEdit, handleDelete, t, tCommon]
  );

  return (
    <>
      {/* 批量操作工具栏 — 由注入渲染器提供，避免 Devices→Switches 耦合 */}
      {renderBatchActions?.({
        selectedPorts: selectedRowKeys as string[],
        onClearSelection,
        hasSsh: false,
        refetch,
        onBatchLocalUpdate: handleBatchLocalUpdate
      })}

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
          extra={
            <Space>
              <Tooltip
                title={
                  !hasSnmpCredential
                    ? t('port.tooltip.needCredential')
                    : deviceOverride === null
                      ? t('port.tooltip.followGlobal', {
                          state: globalEnabled ? t('port.state.on') : t('port.state.off')
                        })
                      : t('port.tooltip.deviceOverride', { follow: t('batchMonitor.modeFollow') })
                }
              >
                <span>
                  <Switch
                    checked={effectiveEnabled}
                    onChange={handleTogglePortSync}
                    disabled={!hasSnmpCredential || setPortSync.isPending}
                    checkedChildren={t('port.switch.sync')}
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
              <Button type="primary" icon={<PlusOutlined />} onClick={() => addModal.open()}>
                {t('port.action.add')}
              </Button>
            </Space>
          }
        />
      </div>

      {/* 端口自动获取提示：未配置 SNMP/Zabbix 凭据时引导用户先添加凭据 */}
      {!hasSnmpCredential && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={t('port.alert.credentialTip')}
          description={t('port.alert.credentialTipDesc')}
        />
      )}

      {/* 端口列表 */}
      <PortTable
        columns={columns}
        dataSource={filteredPorts}
        loading={isLoading}
        rowSelection={rowSelection}
        highlightPort={highlightPort}
      />

      {/* 新增端口弹窗 */}
      <PortBatchAddModal
        deviceId={deviceId}
        open={addModal.isOpen}
        onClose={() => addModal.close()}
      />

      {/* 编辑端口弹窗 */}
      <PortEditModal
        deviceId={deviceId}
        port={editModal.isOpen ? editingPort : null}
        onClose={() => {
          editModal.close();
          setEditingPort(null);
        }}
      />
    </>
  );
}
