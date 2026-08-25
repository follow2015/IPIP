/**
 * useBatchAddTab — BatchAddTab 主状态 hook
 *
 * 把原单体 BatchAddTab 的全部状态（Form.useWatch / 行编辑 / 远程选项 / 联动 effect /
 * 模式判断 / 端口预览 / 提交编排）下沉到本 hook，使组合根只负责渲染。
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Form } from 'antd';

import { useEditableRows } from '@/hooks/useEditableRows';
import { useUPositionAssigner } from '@/hooks/useUPositionAssigner';
import { useBatchDeviceCreate } from '@/hooks/useBatchDeviceCreate';
import { useDeviceList, type CreateDeviceRequest } from '@/services/device';
import { useRoomOptions } from '@/services/room';
import { useCabinetOptions, useCabinetAvailableUPositions } from '@/services/cabinet';
import { useMessage } from '@/hooks/useMessage';
import { post } from '@/services/api-client';
import { useQueryClient } from '@tanstack/react-query';
import { useComponentTemplates } from '@/services/component-template';
import {
  DeviceType,
  DeviceSubtype,
  DEVICE_SUBTYPE_MAP,
  DEVICE_SUBTYPE_LABELS,
  DeviceStatusCode
} from '@/types/enums';
import type { Device, BatchCreateItemResult } from '@/types/models';
import { confirm } from '@/utils/confirm';
import { type DeviceBatchRow, genBatchName, extractMaxIndex } from '../shared';
import { checkUConflict, checkNodePositionConflict } from './conflictCheck';
import { buildCreateDevices, buildSwitchPorts } from './buildCreateRequests';

export type EditableRowsApi<T> = {
  rows: T[];
  addRow: (row: Omit<T, 'key'>) => void;
  addRows: (rows: Omit<T, 'key'>[]) => void;
  updateRow: <K extends keyof T>(key: string, field: K, value: T[K]) => void;
  deleteRow: (key: string) => void;
  copyRow: (key: string, overrides?: Partial<T>) => void;
  resetRows: (rows: Omit<T, 'key'>[]) => void;
  transformRows: (fn: (row: T, index: number) => T) => void;
};

export interface UseBatchAddTabResult {
  form: ReturnType<typeof Form.useForm>[0];
  deviceType?: string;
  deviceSubtype?: string;
  selectedRoomId?: number;
  selectedCabinetId?: number;
  isChassisMode: boolean;
  isNodeMode: boolean;
  isServerType: boolean;
  isNetworkType: boolean;
  isUnmanagedNetwork: boolean;
  subtypeOptions: { label: string; value: string }[];
  roomOptions?: { label: string; value: number }[];
  cabinetOptions?: { label: string; value: number }[];
  chassisOptions: { label: string; value: number }[];
  selectedChassis?: Device;
  availableUCount: number;
  availableUPositions?: unknown;
  portPreview: string[];
  genNodeName: (nodeRow?: number, nodeCol?: number) => string;
  freeNodeSlots?: number;
  rows: DeviceBatchRow[];
  addRow: EditableRowsApi<DeviceBatchRow>['addRow'];
  addRows: EditableRowsApi<DeviceBatchRow>['addRows'];
  updateRow: EditableRowsApi<DeviceBatchRow>['updateRow'];
  deleteRow: EditableRowsApi<DeviceBatchRow>['deleteRow'];
  copyRow: EditableRowsApi<DeviceBatchRow>['copyRow'];
  resetRows: EditableRowsApi<DeviceBatchRow>['resetRows'];
  transformRows: EditableRowsApi<DeviceBatchRow>['transformRows'];
  selectedChassisId?: number;
  setSelectedChassisId: (id?: number) => void;
  addRowCount: number;
  setAddRowCount: (n: number) => void;
  uGap: number;
  setUGap: (n: number) => void;
  batchHeightU: number;
  setBatchHeightU: (n: number) => void;
  handleAddRow: () => void;
  handleAutoAssignU: () => void;
  handleRegenerateNames: () => void;
  handleBatchSetHeightU: () => void;
  handleChassisChange: (id?: number) => void;
  handleSubmit: () => Promise<void>;
  handleRetry: (failedItems: BatchCreateItemResult[]) => void;
  batchCreate: ReturnType<typeof useBatchDeviceCreate>;
}

export function useBatchAddTab(active: boolean): UseBatchAddTabResult {
  const [form] = Form.useForm();
  const message = useMessage();
  const batchCreate = useBatchDeviceCreate();
  const queryClient = useQueryClient();

  const { data: nicComponentTemplates } = useComponentTemplates('nic');

  const deviceType = Form.useWatch('device_type', form) as string | undefined;
  const deviceSubtype = Form.useWatch('device_subtype', form) as string | undefined;
  const selectedRoomId = Form.useWatch('room_id', form) as number | undefined;
  const selectedCabinetId = Form.useWatch('cabinet_id', form) as number | undefined;

  const isChassisMode = deviceSubtype === DeviceSubtype.CHASSIS;
  const isNodeMode = deviceSubtype === DeviceSubtype.NODE;

  const { rows, addRow, addRows, deleteRow, copyRow, updateRow, resetRows, transformRows } =
    useEditableRows<DeviceBatchRow>();

  const { data: availableUPositions } = useCabinetAvailableUPositions(selectedCabinetId ?? 0);
  const { assign: assignU, available: availableUCount } = useUPositionAssigner(availableUPositions);

  const { data: roomOptions } = useRoomOptions();
  const { data: cabinetOptions } = useCabinetOptions(selectedRoomId, false, [1, 2]);

  const [selectedChassisId, setSelectedChassisId] = useState<number | undefined>();

  const isServerType = deviceType === DeviceType.SERVER;
  const isNetworkType = deviceType === DeviceType.NETWORK;
  const hasSsh = Form.useWatch('has_ssh', form) as boolean | undefined;
  const isUnmanagedNetwork = isNetworkType && !hasSsh;

  const portTemplate = Form.useWatch('port_template', form);
  const portSlot = Form.useWatch('port_slot', form);
  const portCard = Form.useWatch('port_card', form);
  const portStart = Form.useWatch('port_start', form);
  const portEnd = Form.useWatch('port_end', form);
  const portCustomPrefix = Form.useWatch('port_custom_prefix', form);

  const portPreview = useMemo(() => {
    const ports = buildSwitchPorts({
      template: portTemplate,
      slot: portSlot,
      card: portCard,
      start: portStart,
      end: portEnd,
      customPrefix: portCustomPrefix
    });
    return ports ? ports.map((p) => p.port_name).slice(0, 200) : [];
  }, [portTemplate, portSlot, portCard, portStart, portEnd, portCustomPrefix]);

  const { data: chassisData } = useDeviceList({
    is_chassis: isNodeMode ? 1 : undefined,
    room_id: isNodeMode ? selectedRoomId : undefined,
    per_page: 200
  });
  const { data: batchChassisNodesData } = useDeviceList({
    device_subtype: isNodeMode ? 'node' : undefined,
    room_id: isNodeMode ? selectedRoomId : undefined,
    per_page: 999
  });
  const chassisOptions = useMemo(() => {
    const list = chassisData?.items ?? [];
    const allNodes = batchChassisNodesData?.items ?? [];
    return list
      .filter((chassis) => {
        const nodeCount = allNodes.filter((n) => n.parent_device_id === chassis.id).length;
        if (chassis.total_nodes && nodeCount >= chassis.total_nodes) return false;
        return true;
      })
      .map((chassis) => {
        const currentNodeCount = allNodes.filter((n) => n.parent_device_id === chassis.id).length;
        const maxNodes = chassis.total_nodes ?? '∞';
        return {
          label: `${chassis.device_name} (${currentNodeCount}/${maxNodes}节点)`,
          value: chassis.id
        };
      });
  }, [chassisData, batchChassisNodesData]);

  const selectedChassis = useMemo(
    () => chassisData?.items?.find((d: Device) => d.id === selectedChassisId),
    [chassisData, selectedChassisId]
  );

  const freeNodeSlots = useMemo(() => {
    if (!isNodeMode || !selectedChassisId || !selectedChassis) return undefined;
    const max = selectedChassis.total_nodes ?? 0;
    const occupied = (batchChassisNodesData?.items ?? []).filter(
      (n) => n.parent_device_id === selectedChassisId
    ).length;
    return max - occupied;
  }, [isNodeMode, selectedChassisId, selectedChassis, batchChassisNodesData]);

  const genNodeName = useCallback(
    (nodeRow?: number, nodeCol?: number): string => {
      if (!selectedChassis || !nodeRow || !nodeCol) return '';
      const nodeCols = selectedChassis.node_cols || 1;
      const pos = (nodeRow - 1) * nodeCols + nodeCol;
      const pattern = selectedChassis.node_naming_pattern || '{chassis}-Node{pos}';
      return pattern
        .replace('{chassis}', selectedChassis.device_name)
        .replace('{pos}', String(pos))
        .replace('{row}', String(nodeRow))
        .replace('{col}', String(nodeCol));
    },
    [selectedChassis]
  );

  const subtypeOptions = useMemo(() => {
    if (!deviceType) return [];
    return (DEVICE_SUBTYPE_MAP[deviceType as DeviceType] ?? []).map((st) => ({
      label: DEVICE_SUBTYPE_LABELS[st],
      value: st
    }));
  }, [deviceType]);

  const prevActiveRef = useRef(false);
  useEffect(() => {
    if (active && !prevActiveRef.current) {
      form.resetFields();
      resetRows([
        {
          device_name: genBatchName(DeviceType.SERVER, 1),
          device_model: '',
          serial_number: '',
          u_position: null,
          height_u: 1,
          status: DeviceStatusCode.AVAILABLE
        },
        {
          device_name: genBatchName(DeviceType.SERVER, 2),
          device_model: '',
          serial_number: '',
          u_position: null,
          height_u: 1,
          status: DeviceStatusCode.AVAILABLE
        },
        {
          device_name: genBatchName(DeviceType.SERVER, 3),
          device_model: '',
          serial_number: '',
          u_position: null,
          height_u: 1,
          status: DeviceStatusCode.AVAILABLE
        }
      ]);
      batchCreate.reset();
    }
    prevActiveRef.current = active;
  }, [active]);

  const prevDeviceTypeRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (
      prevDeviceTypeRef.current !== undefined &&
      prevDeviceTypeRef.current !== deviceType &&
      deviceType
    ) {
      form.setFieldValue('device_subtype', undefined);
      transformRows((row, i) => ({ ...row, device_name: genBatchName(deviceType, i + 1) }));
    }
    prevDeviceTypeRef.current = deviceType;
  }, [deviceType]);

  const prevRoomRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (prevRoomRef.current !== undefined && prevRoomRef.current !== selectedRoomId) {
      form.setFieldValue('cabinet_id', undefined);
    }
    prevRoomRef.current = selectedRoomId;
  }, [selectedRoomId]);


  const [addRowCount, setAddRowCount] = useState(1);
  const [batchHeightU, setBatchHeightU] = useState<number>(1);
  const [uGap, setUGap] = useState<number>(0);

  const handleAddRow = () => {
    const dt = deviceType ?? DeviceType.SERVER;
    const count = Math.max(1, Math.min(addRowCount, 50 - rows.length));
    if (count <= 0) {
      message.warning('最多 50 行');
      return;
    }
    const newRows: Omit<DeviceBatchRow, 'key'>[] = Array.from({ length: count }, (_, i) => ({
      device_name: isNodeMode ? '' : genBatchName(dt, rows.length + i + 1),
      device_model: '',
      serial_number: '',
      u_position: isNodeMode ? null : null,
      height_u: isNodeMode ? 0 : 1,
      status: DeviceStatusCode.AVAILABLE,
      node_rows: isChassisMode ? (form.getFieldValue('node_rows') ?? 2) : undefined,
      node_cols: isChassisMode ? (form.getFieldValue('node_cols') ?? 2) : undefined,
      parent_device_id: isNodeMode ? selectedChassisId : undefined
    }));
    addRows(newRows);
  };

  const handleAutoAssignU = () => {
    if (!availableUCount) {
      message.warning('当前机柜无可用 U 位');
      return;
    }
    const updated = assignU(rows, uGap);
    resetRows(updated.map(({ key: _key, ...r }) => r));
  };

  const handleRegenerateNames = () => {
    const dt = deviceType ?? DeviceType.SERVER;
    const startIdx = extractMaxIndex(rows.map((r) => r.device_name)) + 1;
    transformRows((row, i) => ({ ...row, device_name: genBatchName(dt, startIdx + i) }));
  };

  const handleBatchSetHeightU = () => {
    if (batchHeightU < 1 || batchHeightU > 42) {
      message.warning('U高须在 1-42 之间');
      return;
    }
    transformRows((row) => ({ ...row, height_u: batchHeightU }));
  };


  const handleSubmit = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }

    if (isNodeMode && !selectedChassisId) {
      message.error('请选择所属机箱');
      return;
    }

    if (isNodeMode && selectedChassisId && selectedChassis) {
      const maxNodes = selectedChassis.total_nodes ?? 0;
      const occupiedCount = (batchChassisNodesData?.items ?? []).filter(
        (n) => n.parent_device_id === selectedChassisId
      ).length;
      const availableCount = maxNodes - occupiedCount;
      if (rows.length > availableCount) {
        message.error(
          `机箱空余节点位置不足：仅剩 ${availableCount} 个空位，当前 ${rows.length} 行`
        );
        return;
      }
    }

    if (isNodeMode) {
      const conflict = checkNodePositionConflict(rows);
      if (conflict) {
        message.error(conflict);
        return;
      }
    }

    if (!isNodeMode) {
      const conflict = checkUConflict(rows);
      if (conflict) {
        message.error(conflict);
        return;
      }
    }

    const values = form.getFieldsValue();
    if (!isNodeMode) {
      const noUPositionRows = rows.filter((r) => r.u_position == null);
      if (noUPositionRows.length > 0 && values.cabinet_id) {
        const confirmed = await new Promise<boolean>((resolve) => {
          confirm({
            title: '部分设备未分配U位',
            content: `有 ${noUPositionRows.length} 台设备未指定U位，创建后将放入机柜但无U位信息。是否继续？`,
            okText: '继续创建',
            cancelText: '取消',
            onOk: () => resolve(true),
            onCancel: () => resolve(false)
          });
        });
        if (!confirmed) return;
      }
    }

    const devices: CreateDeviceRequest[] = buildCreateDevices({
      rows,
      values,
      isNodeMode,
      isNetworkType,
      isChassisMode,
      isServerType,
      selectedChassis,
      nicComponentTemplates: nicComponentTemplates ?? []
    });

    try {
      const result = await batchCreate.submit(devices);
      if (result?.failed_count === 0) {
        const nodeHint = isChassisMode ? '（已为每台机箱自动生成子节点）' : '';
        message.success(`批量创建成功：${result.success_count} 台${nodeHint}`);
      }
      queryClient.invalidateQueries({ queryKey: ['cabinets'] });

      const createdIds: number[] =
        result?.results
          ?.filter((r: BatchCreateItemResult) => r.success && r.device_id)
          .map((r: BatchCreateItemResult) => r.device_id!) ?? [];

      if (isNetworkType && !values.has_ssh && createdIds.length > 0) {
        const ports = buildSwitchPorts({
          template: values.port_template,
          slot: values.port_slot,
          card: values.port_card,
          start: values.port_start,
          end: values.port_end,
          customPrefix: values.port_custom_prefix
        });
        if (ports && ports.length > 0) {
          try {
            let portFailCount = 0;
            const BATCH_SIZE = 5;
            for (let i = 0; i < createdIds.length; i += BATCH_SIZE) {
              const batch = createdIds.slice(i, i + BATCH_SIZE);
              const results = await Promise.all(
                batch.map((deviceId) =>
                  post('/devices/switch-ports/batch', { device_id: deviceId, ports })
                    .then(() => true)
                    .catch(() => false)
                )
              );
              portFailCount += results.filter((ok) => !ok).length;
            }
            if (portFailCount > 0) {
              message.warning(
                `端口生成：${createdIds.length - portFailCount} 台成功，${portFailCount} 台失败，请检查`
              );
            } else {
              message.success(`已为 ${createdIds.length} 台设备各生成 ${ports.length} 个端口`);
            }
          } catch {
            /* 端口创建失败不阻断 */
          }
        }
      }

    } catch (err) {
      message.error(err instanceof Error ? err.message : '提交失败');
    }
  };

  const handleRetry = (failedItems: BatchCreateItemResult[]) => {
    batchCreate.closeResult();
    const failedIdx = batchCreate.getFailedIndices(failedItems);
    resetRows(rows.filter((_, i) => failedIdx.has(i)).map(({ key: _k, ...r }) => r));
    message.info('已保留失败项，请修正后重新提交');
  };

  const handleChassisChange = useCallback(
    (id?: number) => {
      setSelectedChassisId(id);
      if (!id) return;
      const chassis = chassisData?.items?.find((d: Device) => d.id === id);
      if (!chassis) return;
      const nodeCols = chassis.node_cols || 1;
      const nodeRows = chassis.node_rows || 1;
      const pattern = chassis.node_naming_pattern || '{NAME}-Node{POS}';
      let outOfRangeCount = 0;
      transformRows((row) => {
        const rowOutOfRange = row.node_row != null && row.node_row > nodeRows;
        const colOutOfRange = row.node_col != null && row.node_col > nodeCols;
        if (rowOutOfRange || colOutOfRange) outOfRangeCount += 1;
        const newNodeRow = rowOutOfRange ? undefined : row.node_row;
        const newNodeCol = colOutOfRange ? undefined : row.node_col;
        const pos = newNodeRow && newNodeCol ? (newNodeRow - 1) * nodeCols + newNodeCol : 0;
        const name =
          chassis && pos > 0
            ? pattern
                .replace('{NAME}', chassis.device_name)
                .replace('{POS}', String(pos))
                .replace('{ROW}', String(newNodeRow ?? ''))
                .replace('{COL}', String(newNodeCol ?? ''))
            : row.device_name;
        return {
          ...row,
          parent_device_id: id,
          device_name: name,
          node_row: newNodeRow,
          node_col: newNodeCol
        };
      });
      if (outOfRangeCount > 0) {
        message.warning(`${outOfRangeCount} 行的节点位置超出新机箱范围，已清空`);
      }
    },
    [chassisData, transformRows, message]
  );

  return {
    form,
    deviceType,
    deviceSubtype,
    selectedRoomId,
    selectedCabinetId,
    isChassisMode,
    isNodeMode,
    isServerType,
    isNetworkType,
    isUnmanagedNetwork,
    subtypeOptions,
    roomOptions: roomOptions as { label: string; value: number }[] | undefined,
    cabinetOptions: cabinetOptions as { label: string; value: number }[] | undefined,
    chassisOptions,
    selectedChassis,
    availableUCount,
    availableUPositions,
    portPreview,
    genNodeName,
    freeNodeSlots,
    rows,
    addRow,
    addRows,
    updateRow,
    deleteRow,
    copyRow,
    resetRows,
    transformRows,
    selectedChassisId,
    setSelectedChassisId,
    addRowCount,
    setAddRowCount,
    uGap,
    setUGap,
    batchHeightU,
    setBatchHeightU,
    handleAddRow,
    handleAutoAssignU,
    handleRegenerateNames,
    handleBatchSetHeightU,
    handleChassisChange,
    handleSubmit,
    handleRetry,
    batchCreate
  };
}
