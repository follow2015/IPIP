/**
 * useCloneTab — 克隆复制向导主状态 hook
 *
 * 承接原 CloneTab 的步骤控制、模板数据、节点模式、U位分配、行编辑、
 * 与全部提交处理逻辑；把「模板 → 创建请求」的纯映射下沉到 cloneBuild.ts，
 * 本 hook 只做编排（校验 / 提交 / 结果处理）。
 */
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useEditableRows } from '@/hooks/useEditableRows';
import { useBatchDeviceCreate } from '@/hooks/useBatchDeviceCreate';
import { useDeviceDetail, useDeviceList } from '@/services/device';
import {
  useCabinetOptions,
  useCabinetAvailableUPositions,
  useBatchAllocateUPositions
} from '@/services/cabinet';
import { useMessage } from '@/hooks/useMessage';
import { useQueryClient } from '@tanstack/react-query';
import { DeviceSubtype } from '@/types/enums';
import type { Device, BatchCreateItemResult } from '@/types/models';
import { genCloneName, extractMaxIndex } from '../shared';
import { buildCloneRequests, checkNodePositionConflict } from './cloneBuild';
import { buildCloneColumns } from './cloneColumns';
import { useTranslation } from 'react-i18next';
import { getDeviceStatusMeta } from '@/types/statusMeta';
import type { DeviceBatchRow } from '../shared';

export interface CloneTabProps {
  active: boolean;
  templateDeviceId?: number;
  onClose: (refresh?: boolean) => void;
}

export function useCloneTab({ active, templateDeviceId, onClose }: CloneTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const batchCreate = useBatchDeviceCreate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState(0);

  const [templateId, setTemplateId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [cloneCount, setCloneCount] = useState(1);
  const [targetCabinetId, setTargetCabinetId] = useState<number | null>(null);

  const { data: templateDetail, isLoading: isTemplateLoading } = useDeviceDetail(templateId ?? 0);
  const isChassisTemplate = templateDetail?.device_subtype === DeviceSubtype.CHASSIS;
  const isNodeTemplate = templateDetail?.device_subtype === DeviceSubtype.NODE;

  const [cloneChassisId, setCloneChassisId] = useState<number | undefined>();
  const { data: chassisData } = useDeviceList({
    is_chassis: isNodeTemplate ? 1 : undefined,
    room_id: undefined,
    per_page: 200
  });
  const { data: chassisNodesData } = useDeviceList({
    parent_device_id: cloneChassisId ?? 0,
    per_page: 999
  });
  const cloneChassisOptions = useMemo(() => {
    const list = chassisData?.items ?? [];
    const allNodes = chassisNodesData?.items ?? [];
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
          label: t('form.nodeAssoc.chassis.option', {
            name: chassis.device_name,
            used: currentNodeCount,
            max: maxNodes
          }),
          value: chassis.id
        };
      });
  }, [chassisData, chassisNodesData, t]);
  const selectedChassis = useMemo(
    () => chassisData?.items?.find((d: Device) => d.id === cloneChassisId),
    [chassisData, cloneChassisId]
  );
  const cloneAvailablePositions = useMemo(() => {
    if (!cloneChassisId || !selectedChassis) return [];
    const maxNodes = selectedChassis.total_nodes ?? 0;
    const occupied = new Set(
      (chassisNodesData?.items ?? [])
        .map((n) => n.node_position)
        .filter((p): p is number => p != null)
    );
    const positions: number[] = [];
    for (let i = 1; i <= maxNodes; i++) {
      if (!occupied.has(i)) positions.push(i);
    }
    return positions;
  }, [cloneChassisId, selectedChassis, chassisNodesData]);
  const genCloneNodeName = useCallback(
    (nodeRow?: number, nodeCol?: number): string => {
      if (!selectedChassis || !nodeRow || !nodeCol) return '';
      const nodeCols = selectedChassis.node_cols || 1;
      const pos = (nodeRow - 1) * nodeCols + nodeCol;
      const pattern = selectedChassis.node_naming_pattern || '{NAME}-Node{POS}';
      return pattern
        .replace('{NAME}', selectedChassis.device_name)
        .replace('{POS}', String(pos))
        .replace('{ROW}', String(nodeRow))
        .replace('{COL}', String(nodeCol));
    },
    [selectedChassis]
  );

  const { rows: diffRows, updateRow, resetRows, transformRows } = useEditableRows<DeviceBatchRow>();

  const effectiveCabinetId = targetCabinetId ?? templateDetail?.cabinet_id ?? 0;
  const { data: availableUPositions } = useCabinetAvailableUPositions(effectiveCabinetId);
  const { data: cabinetOptionsData } = useCabinetOptions(undefined, false, [1, 2]);
  const cabinetOptions = cabinetOptionsData ?? [];
  const availableUCount = availableUPositions?.length ?? 0;
  const assignUMutation = useBatchAllocateUPositions();

  const { data: deviceListData, isLoading: isDeviceListLoading } = useDeviceList({
    search: searchText || undefined,
    per_page: 20
  });

  const deviceSelectOptions = useMemo(
    () =>
      (deviceListData?.items ?? []).map((d: Device) => ({
        label: t('addModal.clone.deviceOption', {
          name: d.device_name,
          cabinet: d.cabinet_number ?? t('addModal.unassigned'),
          status: getDeviceStatusMeta(d.status, t)?.label ?? ''
        }),
        value: d.id
      })),
    [deviceListData, t]
  );

  const prevActiveRef = useRef(false);
  useEffect(() => {
    if (active && !prevActiveRef.current) {
      setStep(0);
      setSearchText('');
      setCloneCount(1);
      setTargetCabinetId(null);
      setCloneChassisId(undefined);
      resetRows([]);
      batchCreate.reset();
      setTemplateId(templateDeviceId && templateDeviceId > 0 ? templateDeviceId : null);
    }
    prevActiveRef.current = active;
  }, [active, templateDeviceId]);

  const handleNext = () => {
    if (!templateDetail) {
      message.warning(t('addModal.clone.selectTemplateFirst'));
      return;
    }
    if (cloneCount < 1 || cloneCount > 50) {
      message.warning(t('addModal.clone.countRange'));
      return;
    }

    if (isNodeTemplate && !cloneChassisId) {
      message.warning(t('addModal.clone.nodeNeedChassis'));
      return;
    }

    if (isNodeTemplate && cloneChassisId && cloneAvailablePositions.length < cloneCount) {
      message.warning(
        t('addModal.clone.nodeSlotInsufficient', {
          count: cloneAvailablePositions.length,
          required: cloneCount
        })
      );
      return;
    }

    const baseName = templateDetail.device_name;
    const heightU = templateDetail.height_u ?? 1;

    const initRows: Omit<DeviceBatchRow, 'key'>[] = Array.from({ length: cloneCount }, (_, i) => {
      if (isNodeTemplate && cloneChassisId && selectedChassis) {
        const pos = cloneAvailablePositions[i];
        const nodeCols = selectedChassis.node_cols || 1;
        const nodeRow = Math.ceil(pos / nodeCols);
        const nodeCol = ((pos - 1) % nodeCols) + 1;
        const pattern = selectedChassis.node_naming_pattern || '{NAME}-Node{POS}';
        const name = pattern
          .replace('{NAME}', selectedChassis.device_name)
          .replace('{POS}', String(pos))
          .replace('{ROW}', String(nodeRow))
          .replace('{COL}', String(nodeCol));
        return {
          device_name: name,
          serial_number: '',
          u_position: null,
          status: templateDetail.status,
          height_u: 0,
          parent_device_id: cloneChassisId,
          node_row: nodeRow,
          node_col: nodeCol
        };
      }
      if (isChassisTemplate) {
        return {
          device_name: genCloneName(baseName, i + 1),
          serial_number: '',
          u_position: null,
          status: templateDetail.status,
          height_u: heightU,
          node_rows: templateDetail.node_rows ?? 2,
          node_cols: templateDetail.node_cols ?? 2
        };
      }
      return {
        device_name: genCloneName(baseName, i + 1),
        serial_number: '',
        u_position: null,
        status: templateDetail.status,
        height_u: heightU
      };
    });
    resetRows(initRows);
    setStep(1);
  };

  const handleAutoAssignU = () => {
    if (!availableUCount) {
      message.warning(t('addModal.clone.noAvailableU'));
      return;
    }
    assignUMutation.mutate(
      {
        cabinetId: effectiveCabinetId,
        devices: diffRows.map((r) => ({
          key: r.key,
          height_u: r.height_u ?? 1,
          u_position: r.u_position
        }))
      },
      {
        onSuccess: (res) => {
          if (!res.success) {
            message.warning(res.message || t('addModal.message.cabinetSpaceInsufficient'));
            return;
          }
          const uByKey = new Map(res.allocations.map((a) => [a.key, a.u_position]));
          resetRows(
            diffRows
              .map((r) => {
                const u = uByKey.get(r.key);
                return u != null ? { ...r, u_position: u } : r;
              })
              .map(({ key: _k, ...rest }) => rest)
          );
          message.success(res.message || t('addModal.message.autoAssignDone'));
        },
        onError: () => message.error(t('addModal.message.allocateFailed'))
      }
    );
  };

  const handleRegenerateNames = () => {
    if (!templateDetail) return;
    const startIdx = extractMaxIndex(diffRows.map((r) => r.device_name)) + 1;
    transformRows((row, i) => ({
      ...row,
      device_name: genCloneName(templateDetail.device_name, startIdx + i)
    }));
  };

  const handleSubmit = async () => {
    if (!templateDetail) return;

    if (isNodeTemplate && cloneChassisId) {
      if (checkNodePositionConflict(diffRows, selectedChassis)) {
        message.error(t('addModal.clone.duplicateNodePosition'));
        return;
      }
    }

    const devices = buildCloneRequests(templateDetail as Device, diffRows, {
      targetCabinetId,
      isNodeTemplate,
      isChassisTemplate,
      selectedChassis
    });

    try {
      const result = await batchCreate.submit(devices);
      if (result?.failed_count === 0) {
        const hint = isChassisTemplate ? t('addModal.hint.autoNodesSuffix') : '';
        message.success(t('addModal.clone.success', { count: result.success_count, hint }));
      }
      queryClient.invalidateQueries({ queryKey: ['cabinets'] });
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('addModal.message.submitFailed'));
    }
  };

  const handleRetry = (failedItems: BatchCreateItemResult[]) => {
    batchCreate.closeResult();
    const failedIdx = batchCreate.getFailedIndices(failedItems);
    resetRows(diffRows.filter((_, i) => failedIdx.has(i)).map(({ key: _k, ...r }) => r));
    message.info(t('addModal.message.retryHint'));
  };

  const handleResultClose = () => {
    batchCreate.closeResult();
    if (batchCreate.result && batchCreate.result.success_count > 0) onClose(true);
  };

  const diffColumns = useMemo(
    () =>
      buildCloneColumns({
        updateRow,
        genCloneNodeName,
        isChassisTemplate,
        isNodeTemplate,
        t: { d: t, c: tCommon }
      }),
    [updateRow, genCloneNodeName, isChassisTemplate, isNodeTemplate, t, tCommon]
  );

  return {
    step,
    setStep,
    templateId,
    setTemplateId,
    searchText,
    setSearchText,
    cloneCount,
    setCloneCount,
    targetCabinetId,
    setTargetCabinetId,
    templateDetail,
    isTemplateLoading,
    isChassisTemplate,
    isNodeTemplate,
    cloneChassisId,
    setCloneChassisId,
    cloneChassisOptions,
    selectedChassis,
    cloneAvailablePositions,
    diffRows,
    updateRow,
    resetRows,
    transformRows,
    effectiveCabinetId,
    availableUPositions,
    cabinetOptions,
    availableUCount,
    deviceSelectOptions,
    isDeviceListLoading,
    handleNext,
    handleAutoAssignU,
    handleRegenerateNames,
    handleSubmit,
    handleRetry,
    handleResultClose,
    diffColumns,
    batchCreate
  };
}
