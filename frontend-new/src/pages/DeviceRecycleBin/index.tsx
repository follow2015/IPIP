import { useConfirm, type ConfirmFn } from '@/utils/confirm';
import { useState, useCallback, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Space, Select, Tag, Input, Typography, Alert, Modal } from 'antd';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import { DeleteOutlined, UndoOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { formatDateTime } from '@/utils/format';
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
import { DeviceType } from '@/types/enums';
import { getDeviceTypeMeta, getDeviceTypeOptions, type DeviceT } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

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


function buildColumns(handlers: {
  confirm: ConfirmFn;
  onRestore: (r: Device) => void;
  onPermanentDelete: (r: Device) => void;
  t: { d: DeviceT; c: TFunction<'common'> };
}): any[] {
  const { confirm, t } = handlers;
  return [
    {
      title: t.d('field.name'),
      dataIndex: 'device_name',
      key: 'device_name',
      width: 180
    },
    {
      title: t.d('basic.field.deviceType'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (val: string) => {
        const entry = getDeviceTypeMeta(val as DeviceType, t.d);
        return <Tag>{entry?.label || val}</Tag>;
      }
    },
    {
      title: t.d('field.managementIp'),
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140
    },
    {
      title: t.d('recycleBin.column.originalCabinet'),
      key: 'original_cabinet',
      width: 120,
      render: (_: unknown, record: Device) => {
        const loc = record.deleted_location_snapshot;
        return loc?.cabinet_number || record.cabinet_number || '-';
      }
    },
    {
      title: t.d('recycleBin.column.originalUPosition'),
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
      title: t.d('recycleBin.column.deletedAt'),
      dataIndex: 'deleted_at',
      key: 'deleted_at',
      width: 180,
      render: (val: string) => formatDateTime(val)
    },
    {
      title: t.c('field.actions'),
      key: 'action',
      width: 160,
      render: (_: unknown, record: Device) => (
        <Space size="small">
          <Button type="link" icon={<UndoOutlined />} onClick={() => handlers.onRestore(record)}>
            {t.d('recycleBin.action.restore')}
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              confirm({
                title: t.d('recycleBin.confirm.permanentDeleteTitle'),
                content: t.d('recycleBin.confirm.permanentDeleteContent'),
                okText: t.c('action.ok'),
                cancelText: t.c('action.cancel'),
                okButtonProps: { danger: true },
                onOk: () => handlers.onPermanentDelete(record)
              })
            }
          >
            {t.d('recycleBin.action.permanentDelete')}
          </Button>
        </Space>
      )
    }
  ];
}


const RECYCLE_BIN_FILTER_RESETS = {
  room_id: ['cabinet_id']
};

export default function DeviceRecycleBin() {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const { t: tNetwork } = useTranslation('network');
  const confirm = useConfirm();
  const table = useTable({ filterResets: RECYCLE_BIN_FILTER_RESETS });
  const msg = useMessage();

  const restoreModal = useDisclosure();
  const [restoringDevice, setRestoringDevice] = useState<Device | null>(null);
  const [restoreCabinetId, setRestoreCabinetId] = useState<number | undefined>();
  const [restoreUPosition, setRestoreUPosition] = useState<number | undefined>();
  const [locationConflict, setLocationConflict] = useState(false);
  const [conflictMsg, setConflictMsg] = useState('');

  const batchRestoreModal = useDisclosure();
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
    restoreModal.open();
  }, []);

  const doRestore = useCallback(() => {
    if (!restoringDevice) return;
    const isChildNode = !!restoringDevice.deleted_location_snapshot?.parent_device_id;
    if (locationConflict && !restoreCabinetId && !isChildNode) {
      msg.warning(t('recycleBin.message.conflictSelectCabinet'));
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
            const parts = [t('recycleBin.message.restoreSuccess')];
            if (result.auto_assigned_u_position) {
              parts.push(t('recycleBin.message.autoAssigned', { u: result.auto_assigned_u_position }));
            }
            if (result.children_restored) {
              parts.push(
                t('recycleBin.message.childrenRestored', { count: result.children_restored })
              );
            }
            msg.success(parts.join(''));
            restoreModal.close();
          } else if (result?.location_conflict) {
            setLocationConflict(true);
            const conflicts = result.conflict_devices || [];
            const devices = conflicts.map((d) => d.name).join(', ');
            if (isChildNode) {
              setConflictMsg(
                t('recycleBin.message.nodePositionOccupied', { devices })
              );
            } else {
              setConflictMsg(t('recycleBin.message.uPositionOccupied', { devices }));
            }
          }
        },
        onError: () => msg.error(t('recycleBin.message.restoreFailed'))
      }
    );
  }, [restoringDevice, restoreCabinetId, restoreUPosition, locationConflict, restoreMutation, msg, t]);

  const handleBatchRestore = useCallback(() => {
    setBatchRestoreCabinetId(undefined);
    setBatchRestoreUPosition(undefined);
    batchRestoreModal.open();
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
          msg.success(
            t('recycleBin.message.batchRestoreSuccess', { count: result?.success?.length || 0 })
          );
          batch.clear();
          batchRestoreModal.close();
        },
        onError: () => msg.error(t('recycleBin.message.batchRestoreFailed'))
      }
    );
  }, [batch, batchRestoreCabinetId, batchRestoreUPosition, batchRestoreMutation, msg, t]);

  const handlePermanentDelete = useCallback(
    (record: Device) => {
      permanentDeleteMutation.mutate(record.id, {
        onSuccess: () => msg.success(t('recycleBin.message.permanentDeleted')),
        onError: () => msg.error(t('recycleBin.message.permanentDeleteFailed'))
      });
    },
    [permanentDeleteMutation, msg, t]
  );

  const handleBatchPermanentDelete = useCallback(() => {
    confirm({
      title: t('recycleBin.confirm.batchPermanentDeleteTitle'),
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <Text type="danger">{t('recycleBin.confirm.irreversible')}</Text>
          <br />
          {t('recycleBin.confirm.batchPermanentDeleteContent', { count: batch.count })}
        </div>
      ),
      okText: t('recycleBin.confirm.batchPermanentDeleteOk'),
      okButtonProps: { danger: true },
      cancelText: tCommon('action.cancel'),
      onOk: () => {
        batchPermanentDeleteMutation.mutate(batch.selectedKeys.map(Number), {
          onSuccess: (res) => {
            const result = res as unknown as BatchResult;
            msg.success(
              t('recycleBin.message.batchPermanentDeleteSuccess', {
                count: result?.success?.length || 0
              })
            );
            batch.clear();
          },
          onError: () => msg.error(t('recycleBin.message.batchPermanentDeleteFailed'))
        });
      }
    });
  }, [confirm, batch, batchPermanentDeleteMutation, msg, t, tCommon]);

  const columns = useMemo(
    () =>
      buildColumns({
        confirm,
        onRestore: handleRestore,
        onPermanentDelete: handlePermanentDelete,
        t: { d: t, c: tCommon }
      }),
    [confirm, handleRestore, handlePermanentDelete, t, tCommon]
  );

  const toolbar = (
    <FilterBar
      filters={[
        {
          key: 'date_range',
          label: t('recycleBin.filter.deletedDate'),
          type: 'rangePicker',
          placeholders: [t('recycleBin.filter.deletedStart'), t('recycleBin.filter.deletedEnd')]
        },
        {
          key: 'room_id',
          label: tNetwork('networkList.field.room'),
          type: 'select',
          options: roomOptions.data ?? [],
          width: 140
        },
        {
          key: 'cabinet_id',
          label: t('field.cabinet'),
          type: 'select',
          options: cabinetOptions.data ?? [],
          width: 140
        },
        {
          key: 'device_type',
          label: t('basic.field.deviceType'),
          type: 'select',
          options: getDeviceTypeOptions(t),
          width: 120
        }
      ]}
      table={table}
    />
  );

  const batchToolbar = (
    <BatchActionBar count={batch.count} unit={t('batch.unit')} onClear={batch.clear}>
      <Button
        icon={<UndoOutlined />}
        onClick={handleBatchRestore}
        loading={batchRestoreMutation.isPending}
      >
        {t('recycleBin.action.batchRestore')}
      </Button>
      <Button
        danger
        icon={<DeleteOutlined />}
        onClick={handleBatchPermanentDelete}
        loading={batchPermanentDeleteMutation.isPending}
      >
        {t('recycleBin.action.batchPermanentDelete')}
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
        searchPlaceholder={tNetwork('audit.searchPlaceholder')}
        rowSelection={batch.rowSelection}
      />

      {/* 恢复弹窗 */}
      <Modal
        title={t('recycleBin.modal.restoreTitle')}
        open={restoreModal.isOpen}
        onOk={doRestore}
        onCancel={() => restoreModal.close()}
        confirmLoading={restoreMutation.isPending}
        okText={t('recycleBin.modal.confirmRestore')}
      >
        {restoringDevice &&
          (() => {
            const isChildNode = !!restoringDevice.deleted_location_snapshot?.parent_device_id;
            return (
              <div>
                <p>
                  <strong>{t('recycleBin.modal.deviceName')}</strong>
                  {restoringDevice.device_name}
                </p>
                {isChildNode && (
                  <Alert
                    type="info"
                    showIcon
                    title={t('recycleBin.modal.childNodeOnlyTitle')}
                    description={t('recycleBin.modal.childNodeOnlyDesc')}
                    style={{ marginBottom: 16 }}
                  />
                )}
                {!isChildNode && locationConflict && (
                  <Alert
                    type="error"
                    showIcon
                    title={t('recycleBin.modal.uPositionOccupiedTitle')}
                    description={conflictMsg}
                    style={{ marginBottom: 16 }}
                  />
                )}
                {isChildNode && locationConflict && (
                  <Alert
                    type="error"
                    showIcon
                    title={t('recycleBin.modal.nodePositionOccupiedTitle')}
                    description={conflictMsg}
                    style={{ marginBottom: 16 }}
                  />
                )}
                {!isChildNode && !restoreCabinetId && !locationConflict ? (
                  <Alert
                    type="info"
                    showIcon
                    title={t('recycleBin.modal.restoreToOriginalTitle')}
                    description={t('recycleBin.modal.restoreToOriginalDesc', {
                      cabinet: (() => {
                        const loc = restoringDevice.deleted_location_snapshot;
                        return loc?.cabinet_number || restoringDevice.cabinet_number || '-';
                      })(),
                      u: (() => {
                        const loc = restoringDevice.deleted_location_snapshot;
                        const uPos = loc?.u_position ?? restoringDevice.u_position;
                        return uPos != null ? String(uPos) : '-';
                      })()
                    })}
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                {!isChildNode && restoreCabinetId && !restoreUPosition ? (
                  <Alert
                    type="info"
                    showIcon
                    title={t('recycleBin.modal.uAutoAssignTitle')}
                    description={t('recycleBin.modal.uAutoAssignDesc')}
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                {!isChildNode && (
                  <>
                    <Select
                      placeholder={t('recycleBin.modal.selectTargetCabinet')}
                      allowClear
                      style={{ width: '100%', marginBottom: 8 }}
                      options={cabinetOptions.data}
                      value={restoreCabinetId}
                      onChange={setRestoreCabinetId}
                    />
                    <Input
                      placeholder={
                        restoreCabinetId
                          ? t('recycleBin.modal.uStartAuto')
                          : t('recycleBin.modal.uStartOriginal')
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

      {/* 批量恢复弹窗 */}
      <Modal
        title={t('recycleBin.modal.batchRestoreTitle')}
        open={batchRestoreModal.isOpen}
        onOk={doBatchRestore}
        onCancel={() => batchRestoreModal.close()}
        confirmLoading={batchRestoreMutation.isPending}
        okText={t('recycleBin.modal.confirmRestore')}
      >
        <p>{t('recycleBin.modal.batchRestoreCount', { count: batch.count })}</p>
        {!batchRestoreCabinetId ? (
          <Alert
            type="info"
            showIcon
            title={t('recycleBin.modal.restoreToOriginalTitle')}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        {batchRestoreCabinetId && !batchRestoreUPosition ? (
          <Alert
            type="info"
            showIcon
            title={t('recycleBin.modal.uAutoAssignTitle')}
            description={t('recycleBin.modal.uAutoAssignBatchDesc')}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Select
          placeholder={t('recycleBin.modal.selectTargetCabinet')}
          allowClear
          style={{ width: '100%', marginBottom: 8 }}
          options={cabinetOptions.data}
          value={batchRestoreCabinetId}
          onChange={setBatchRestoreCabinetId}
        />
        <Input
          placeholder={
            batchRestoreCabinetId
              ? t('recycleBin.modal.uStartAuto')
              : t('recycleBin.modal.uStartOriginal')
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
