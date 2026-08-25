/**
 * PortManualCrud — 非网管（手动 CRUD）模式的端口区块
 * 工具栏（筛选 + 新增）+ 批量操作 + 端口列表 + 新增/编辑弹窗 + 增删改/批量 handler
 */
import { useCallback, useMemo, useState } from 'react';
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
import { confirm } from '@/utils/confirm';
import { buildManualColumns } from './columns';
import { PortTable } from './PortTable';
import { PortStats } from './PortStats';
import { PortBatchAddModal } from './PortBatchAddModal';
import { PortEditModal } from './PortEditModal';
import { USAGE_STATUS_FILTER_OPTIONS } from './constants';

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
  const message = useMessage();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
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
          message.success(checked ? '已开启端口自动同步' : '已关闭端口自动同步');
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

  
  const handleEdit = useCallback((port: SwitchPort) => {
    setEditingPort(port);
    setEditModalOpen(true);
  }, []);

  
  const handleDelete = useCallback(
    (port: SwitchPort) => {
      confirm({
        title: '确认删除端口',
        content: `确定要删除端口「${port.port_name}」吗？`,
        okButtonProps: { danger: true },
        onOk: async () => {
          await deletePort.mutateAsync(port.id);
          message.success('端口已删除');
        }
      });
    },
    [deletePort, message]
  );

  
  const handleToggleUsageStatus = useCallback(
    (port: SwitchPort) => {
      const newStatus = port.usage_status === 'disabled' ? 'free' : 'disabled';
      const actionText = newStatus === 'disabled' ? '禁用' : '启用';
      confirm({
        title: `确认${actionText}端口`,
        content: `确定要${actionText}端口「${port.port_name}」吗？`,
        onOk: async () => {
          await updateUsageStatus.mutateAsync({ portId: port.id, usageStatus: newStatus });
          message.success(`${actionText}成功`);
        }
      });
    },
    [updateUsageStatus, message]
  );

  
  const handleBatchLocalUpdate = useCallback(
    async (portNames: string[], updates: Record<string, unknown>) => {
      const portsToUpdate = sortedPorts.filter((p) => portNames.includes(p.port_name));
      const results = await Promise.allSettled(
        portsToUpdate.map((port) => updatePort.mutateAsync({ portId: port.id, data: updates }))
      );
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed > 0) {
        message.warning(`批量操作完成，${failed} 个端口更新失败`);
      } else {
        message.success(`已更新 ${portsToUpdate.length} 个端口`);
      }
    },
    [sortedPorts, updatePort, message]
  );

  const columns = useMemo(
    () =>
      buildManualColumns({
        onToggleUsageStatus: handleToggleUsageStatus,
        onEdit: handleEdit,
        onDelete: handleDelete
      }),
    [handleToggleUsageStatus, handleEdit, handleDelete]
  );

  return (
    <>
      {}
      {renderBatchActions?.({
        selectedPorts: selectedRowKeys as string[],
        onClearSelection,
        hasSsh: false,
        refetch,
        onBatchLocalUpdate: handleBatchLocalUpdate
      })}

      {}
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
          extra={
            <Space>
              <Tooltip
                title={
                  !hasSnmpCredential
                    ? '请先添加 SNMP 或 Zabbix 监控凭据后才能开启端口自动同步'
                    : deviceOverride === null
                      ? `跟随全局开关（当前：${globalEnabled ? '开' : '关'}），点击切换为设备级强制开关`
                      : '设备级开关已强制设置，点击"跟随全局"可恢复'
                }
              >
                <span>
                  <Switch
                    checked={effectiveEnabled}
                    onChange={handleTogglePortSync}
                    disabled={!hasSnmpCredential || setPortSync.isPending}
                    checkedChildren="同步"
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
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>
                新增端口
              </Button>
            </Space>
          }
        />
      </div>

      {}
      {!hasSnmpCredential && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="如果有监控凭据，建议先添加 SNMP 或 Zabbix 监控凭据来自动获取端口"
          description="添加监控凭据后，可开启上方「端口同步」开关，系统将在监控轮询时自动同步端口。未添加凭据时开关不可开启。"
        />
      )}

      {}
      <PortTable
        columns={columns}
        dataSource={filteredPorts}
        loading={isLoading}
        rowSelection={rowSelection}
        highlightPort={highlightPort}
      />

      {}
      <PortBatchAddModal
        deviceId={deviceId}
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
      />

      {}
      <PortEditModal
        deviceId={deviceId}
        port={editModalOpen ? editingPort : null}
        onClose={() => {
          setEditModalOpen(false);
          setEditingPort(null);
        }}
      />
    </>
  );
}
