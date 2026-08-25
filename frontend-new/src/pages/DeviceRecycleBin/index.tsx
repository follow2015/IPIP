import { confirm } from '@/utils/confirm';

import { useState, useCallback, useMemo } from 'react';
import { Button, Space, Select, Tag, Input, Popconfirm, Typography, Alert, Modal } from 'antd';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import { DeleteOutlined, UndoOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import {
  useDeletedDeviceList,
  useRestoreDevice,
  useBatchRestoreDevices,
  usePermanentDeleteDevice,
  useBatchPermanentDeleteDevices
} from '@/services/device';
import type { DeletedDeviceQueryParams } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import { useRoomOptions } from '@/services/room';
import { useCabinetOptions } from '@/services/cabinet';
import { useTable } from '@/hooks/useTable';
import type { Device } from '@/types/models';
import { DEVICE_TYPE_MAP, DeviceType } from '@/types/enums';

const { Text } = Typography;


interface DeletedDeviceListData {
  devices: Device[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}


interface RestoreResult {
  restored: boolean;
  location_conflict: boolean;
  conflict_devices: { id: number; name: string }[];
  children_restored: number;
  original_cabinet_id?: number;
  original_u_position?: number;
  auto_assigned_u_position?: number | null;
}


interface BatchResult {
  success: number[];
  failed: { device_id: number; error: string }[];
}


const deviceTypeOptions = Object.entries(DEVICE_TYPE_MAP).map(([value, { label }]) => ({
  value,
  label
}));


function buildColumns(handlers: {
  onRestore: (r: Device) => void;
  onPermanentDelete: (r: Device) => void;
}): any[] {
  return [
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      width: 180
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (val: string) => {
        const entry = DEVICE_TYPE_MAP[val as DeviceType];
        return <Tag>{entry?.label || val}</Tag>;
      }
    },
    {
      title: '管理IP',
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140
    },
    {
      title: '原机柜',
      key: 'original_cabinet',
      width: 120,
      render: (_: unknown, record: Device) => {
        const loc = record.deleted_location_snapshot;
        return loc?.cabinet_number || record.cabinet_number || '-';
      }
    },
    {
      title: '原U位',
      key: 'original_u_position',
      width: 100,
      render: (_: unknown, record: Device) => {
        const loc = record.deleted_location_snapshot;
        const uPos = loc?.u_position ?? record.u_position;
        const heightU = loc?.height_u ?? record.height_u;
        if (uPos == null) return '-';
        return heightU > 1 ? `${uPos}-${Number(uPos) + Number(heightU) - 1}U` : `${uPos}U`;
      }
    },
    {
      title: '删除时间',
      dataIndex: 'deleted_at',
      key: 'deleted_at',
      width: 180,
      render: (val: string) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-')
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: Device) => (
        <Space size="small">
          <Button type="link" icon={<UndoOutlined />} onClick={() => handlers.onRestore(record)}>
            恢复
          </Button>
          <Popconfirm
            title="永久删除"
            description="此操作不可恢复，确定要永久删除该设备吗？"
            onConfirm={() => handlers.onPermanentDelete(record)}
            okText="确定"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              永久删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];
}


export default function DeviceRecycleBin() {
  const table = useTable({
    filterResets: {
      room_id: ['cabinet_id']
    }
  });
  const msg = useMessage();

  
  const [restoreModalOpen, setRestoreModalOpen] = useState(false);
  const [restoringDevice, setRestoringDevice] = useState<Device | null>(null);
  const [restoreCabinetId, setRestoreCabinetId] = useState<number | undefined>();
  const [restoreUPosition, setRestoreUPosition] = useState<number | undefined>();
  const [locationConflict, setLocationConflict] = useState(false);
  const [conflictMsg, setConflictMsg] = useState('');

  
  const [batchRestoreModalOpen, setBatchRestoreModalOpen] = useState(false);
  const [batchRestoreCabinetId, setBatchRestoreCabinetId] = useState<number | undefined>();
  const [batchRestoreUPosition, setBatchRestoreUPosition] = useState<number | undefined>();

  
  const roomOptions = useRoomOptions();
  const cabinetOptions = useCabinetOptions(
    table.filters.room_id ? Number(table.filters.room_id) : undefined,
    true
  );

  
  const dateRangeFilter = table.filters.date_range as string | undefined;
  const [startDate, endDate] = dateRangeFilter
    ? dateRangeFilter.split('~')
    : [undefined, undefined];

  const queryParams: DeletedDeviceQueryParams = {
    page: table.page,
    per_page: table.perPage,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    cabinet_id: table.filters.cabinet_id ? Number(table.filters.cabinet_id) : undefined,
    device_type:
      typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined,
    search: table.search || undefined
  };

  const { data, isLoading } = useDeletedDeviceList(queryParams);
  const restoreMutation = useRestoreDevice();
  const batchRestoreMutation = useBatchRestoreDevices();
  const permanentDeleteMutation = usePermanentDeleteDevice();
  const batchPermanentDeleteMutation = useBatchPermanentDeleteDevices();

  
  const listData = data as unknown as DeletedDeviceListData | undefined;

  
  const batch = useBatchSelection<Device>({
    dataSource: listData?.devices ?? [],
    getRowKey: (r) => String(r.id ?? '')
  });

  
  const handleRestore = useCallback((record: Device) => {
    setRestoringDevice(record);
    setRestoreCabinetId(undefined);
    setRestoreUPosition(undefined);
    setLocationConflict(false);
    setConflictMsg('');
    setRestoreModalOpen(true);
  }, []);

  
  const doRestore = useCallback(() => {
    if (!restoringDevice) return;
    const isChildNode = !!restoringDevice.deleted_location_snapshot?.parent_device_id;
    
    if (locationConflict && !restoreCabinetId && !isChildNode) {
      msg.warning('原U位有冲突，请选择目标机柜（可不填U位，系统将自动分配）');
      return;
    }
    restoreMutation.mutate(
      {
        id: restoringDevice.id,
        cabinet_id: restoreCabinetId,
        u_position: restoreUPosition
      },
      {
        onSuccess: (res) => {
          const result = (res?.data ?? res) as unknown as RestoreResult;
          if (result?.restored) {
            const parts = ['设备恢复成功'];
            if (result.auto_assigned_u_position) {
              parts.push(`，自动分配至 ${result.auto_assigned_u_position}U`);
            }
            if (result.children_restored) {
              parts.push(`，已重建 ${result.children_restored} 个子节点`);
            }
            msg.success(parts.join(''));
            setRestoreModalOpen(false);
          } else if (result?.location_conflict) {
            setLocationConflict(true);
            const conflicts = result.conflict_devices || [];
            if (isChildNode) {
              setConflictMsg(
                `原节点位置已被占用（冲突设备：${conflicts.map((d) => d.name).join(', ')}），请先删除或移走冲突节点后再恢复`
              );
            } else {
              setConflictMsg(
                `原U位已被占用（冲突设备：${conflicts.map((d) => d.name).join(', ')}），请选择目标机柜`
              );
            }
          }
        },
        onError: () => msg.error('恢复失败')
      }
    );
  }, [restoringDevice, restoreCabinetId, restoreUPosition, locationConflict, restoreMutation, msg]);

  
  const handleBatchRestore = useCallback(() => {
    setBatchRestoreCabinetId(undefined);
    setBatchRestoreUPosition(undefined);
    setBatchRestoreModalOpen(true);
  }, []);

  
  const doBatchRestore = useCallback(() => {
    batchRestoreMutation.mutate(
      {
        device_ids: batch.selectedKeys.map(Number),
        cabinet_id: batchRestoreCabinetId,
        u_position: batchRestoreUPosition
      },
      {
        onSuccess: (res) => {
          const result = (res?.data ?? res) as unknown as BatchResult;
          msg.success(`成功恢复 ${result?.success?.length || 0} 个设备`);
          batch.clear();
          setBatchRestoreModalOpen(false);
        },
        onError: () => msg.error('批量恢复失败')
      }
    );
  }, [batch, batchRestoreCabinetId, batchRestoreUPosition, batchRestoreMutation, msg]);

  
  const handlePermanentDelete = useCallback(
    (record: Device) => {
      permanentDeleteMutation.mutate(record.id, {
        onSuccess: () => msg.success('设备已永久删除'),
        onError: () => msg.error('永久删除失败')
      });
    },
    [permanentDeleteMutation, msg]
  );

  
  const handleBatchPermanentDelete = useCallback(() => {
    confirm({
      title: '批量永久删除',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <Text type="danger">此操作不可恢复！</Text>
          <br />
          确定要永久删除选中的 {batch.count} 个设备吗？
        </div>
      ),
      okText: '确定永久删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        batchPermanentDeleteMutation.mutate(batch.selectedKeys.map(Number), {
          onSuccess: (res) => {
            const result = res as unknown as BatchResult;
            msg.success(`成功永久删除 ${result?.success?.length || 0} 个设备`);
            batch.clear();
          },
          onError: () => msg.error('批量永久删除失败')
        });
      }
    });
  }, [batch, batchPermanentDeleteMutation, msg]);

  
  const columns = useMemo(
    () => buildColumns({ onRestore: handleRestore, onPermanentDelete: handlePermanentDelete }),
    [handleRestore, handlePermanentDelete]
  );

  
  const toolbar = (
    <FilterBar
      filters={[
        {
          key: 'date_range',
          label: '删除日期',
          type: 'rangePicker',
          placeholders: ['删除开始', '删除结束']
        },
        {
          key: 'room_id',
          label: '机房',
          type: 'select',
          options: roomOptions.data ?? [],
          width: 140
        },
        {
          key: 'cabinet_id',
          label: '机柜',
          type: 'select',
          options: cabinetOptions.data ?? [],
          width: 140
        },
        {
          key: 'device_type',
          label: '设备类型',
          type: 'select',
          options: deviceTypeOptions,
          width: 120
        }
      ]}
      table={table}
    />
  );

  
  const batchToolbar = (
    <BatchActionBar count={batch.count} unit="台设备" onClear={batch.clear}>
      <Button
        icon={<UndoOutlined />}
        onClick={handleBatchRestore}
        loading={batchRestoreMutation.isPending}
      >
        批量恢复
      </Button>
      <Button
        danger
        icon={<DeleteOutlined />}
        onClick={handleBatchPermanentDelete}
        loading={batchPermanentDeleteMutation.isPending}
      >
        批量永久删除
      </Button>
    </BatchActionBar>
  );

  return (
    <div>
      {toolbar}
      {batchToolbar}
      <DataTable<Device>
        columns={columns}
        dataSource={listData?.devices || []}
        loading={isLoading}
        rowKey={(r) => String(r.id ?? '')}
        tableProps={table}
        total={listData?.total || 0}
        searchable
        searchPlaceholder="搜索IP地址"
        rowSelection={batch.rowSelection}
      />

      {}
      <Modal
        title="恢复设备"
        open={restoreModalOpen}
        onOk={doRestore}
        onCancel={() => setRestoreModalOpen(false)}
        confirmLoading={restoreMutation.isPending}
        okText="确认恢复"
      >
        {restoringDevice &&
          (() => {
            const isChildNode = !!restoringDevice.deleted_location_snapshot?.parent_device_id;
            return (
              <div>
                <p>
                  <strong>设备名称：</strong>
                  {restoringDevice.device_name}
                </p>
                {isChildNode && (
                  <Alert
                    type="info"
                    showIcon
                    title="子节点设备只能恢复到原机箱"
                    description="子节点将恢复到删除前所属的机箱，无需选择机柜"
                    style={{ marginBottom: 16 }}
                  />
                )}
                {!isChildNode && locationConflict && (
                  <Alert
                    type="error"
                    showIcon
                    title="原U位已被占用"
                    description={conflictMsg}
                    style={{ marginBottom: 16 }}
                  />
                )}
                {isChildNode && locationConflict && (
                  <Alert
                    type="error"
                    showIcon
                    title="原节点位置已被占用"
                    description={conflictMsg}
                    style={{ marginBottom: 16 }}
                  />
                )}
                {!isChildNode && !restoreCabinetId && !locationConflict ? (
                  <Alert
                    type="info"
                    showIcon
                    title="将恢复到原位置"
                    description={`机柜：${(() => {
                      const loc = restoringDevice.deleted_location_snapshot;
                      return loc?.cabinet_number || restoringDevice.cabinet_number || '-';
                    })()}，U位：${(() => {
                      const loc = restoringDevice.deleted_location_snapshot;
                      const uPos = loc?.u_position ?? restoringDevice.u_position;
                      return uPos != null ? `${uPos}U` : '-';
                    })()}`}
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                {!isChildNode && restoreCabinetId && !restoreUPosition ? (
                  <Alert
                    type="info"
                    showIcon
                    title="U位将自动分配"
                    description="未填写U位时，系统将自动在所选机柜中寻找可用U位"
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                {!isChildNode && (
                  <>
                    <Select
                      placeholder="选择目标机柜（不选则恢复到原位置）"
                      allowClear
                      style={{ width: '100%', marginBottom: 8 }}
                      options={cabinetOptions.data}
                      value={restoreCabinetId}
                      onChange={setRestoreCabinetId}
                    />
                    <Input
                      placeholder={
                        restoreCabinetId
                          ? 'U位起始位置（不填则自动分配）'
                          : 'U位起始位置（不填则使用原U位）'
                      }
                      type="number"
                      value={restoreUPosition}
                      onChange={(e) =>
                        setRestoreUPosition(e.target.value ? Number(e.target.value) : undefined)
                      }
                    />
                  </>
                )}
              </div>
            );
          })()}
      </Modal>

      {}
      <Modal
        title="批量恢复"
        open={batchRestoreModalOpen}
        onOk={doBatchRestore}
        onCancel={() => setBatchRestoreModalOpen(false)}
        confirmLoading={batchRestoreMutation.isPending}
        okText="确认恢复"
      >
        <p>
          将恢复选中的 <strong>{batch.count}</strong> 个设备
        </p>
        {!batchRestoreCabinetId ? (
          <Alert type="info" showIcon title="将恢复到原位置" style={{ marginBottom: 16 }} />
        ) : null}
        {batchRestoreCabinetId && !batchRestoreUPosition ? (
          <Alert
            type="info"
            showIcon
            title="U位将自动分配"
            description="未填写起始U位时，系统将自动在所选机柜中依次分配可用U位"
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Select
          placeholder="选择目标机柜（不选则恢复到原位置）"
          allowClear
          style={{ width: '100%', marginBottom: 8 }}
          options={cabinetOptions.data}
          value={batchRestoreCabinetId}
          onChange={setBatchRestoreCabinetId}
        />
        <Input
          placeholder={
            batchRestoreCabinetId
              ? 'U位起始位置（不填则自动分配）'
              : 'U位起始位置（不填则使用原U位）'
          }
          type="number"
          value={batchRestoreUPosition}
          onChange={(e) =>
            setBatchRestoreUPosition(e.target.value ? Number(e.target.value) : undefined)
          }
        />
      </Modal>
    </div>
  );
}
