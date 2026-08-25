/**
 * cloneColumns — 克隆差异项表格列定义工厂
 * 根据模式（机箱 / 节点 / 普通）动态生成可编辑列。
 * 与 BatchDeviceTable 共享 buildCommonBatchColumns 的公共可编辑列（序列号 / 行×列 / 行号列号 / U位）。
 */
import { Input, Select } from 'antd';
import { STATUS_OPTIONS, type DeviceBatchRow } from '../shared';
import { buildCommonBatchColumns, type BatchColumns, type EditableRowsApi } from '../batchColumns';

export interface CloneColumnDeps {
  updateRow: EditableRowsApi<DeviceBatchRow>['updateRow'];
  genCloneNodeName: (nodeRow?: number, nodeCol?: number) => string;
  isChassisTemplate: boolean;
  isNodeTemplate: boolean;
}

export function buildCloneColumns({
  updateRow,
  genCloneNodeName,
  isChassisTemplate,
  isNodeTemplate
}: CloneColumnDeps): BatchColumns {
  const base: BatchColumns = [
    { title: '#', width: 44, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      width: 220,
      render: (v: string, r: DeviceBatchRow) => (
        <Input
          size="small"
          value={v}
          onChange={(e) => updateRow(r.key, 'device_name', e.target.value)}
        />
      )
    },
    ...buildCommonBatchColumns({
      updateRow,
      genNodeName: genCloneNodeName,
      isChassis: isChassisTemplate,
      isNode: isNodeTemplate
    }),
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v, r) => (
        <Select
          size="small"
          value={v}
          options={STATUS_OPTIONS}
          style={{ width: '100%' }}
          onChange={(val) => updateRow(r.key, 'status', val)}
        />
      )
    }
  ];

  return base;
}
