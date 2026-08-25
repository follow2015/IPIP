/**
 * batchColumns — 批量创建设备 / 克隆差异项 共用的可编辑列工厂
 *
 * 把 BatchDeviceTable 与 cloneColumns 中重复的设备名称/序列号/机箱「行×列」/
 * 节点「行号/列号」/非节点「U位」/状态 列定义收敛到单一工厂，消除列重复。
 * 设备名称列因两处宽度不同（200/220）由调用方本地保留，不在工厂内。
 */
import { Input, InputNumber } from 'antd';
import type { TableProps } from 'antd';
import { type DeviceBatchRow } from './shared';
import type { EditableRowsApi } from './BatchAddTab/useBatchAddTab';

export type { EditableRowsApi };
export type BatchColumns = NonNullable<TableProps<DeviceBatchRow>['columns']>;

export interface CommonColumnDeps {
  updateRow: EditableRowsApi<DeviceBatchRow>['updateRow'];
  genNodeName: (nodeRow?: number, nodeCol?: number) => string;
  isChassis: boolean;
  isNode: boolean;
  widths?: {
    serial?: number;
    layout?: number;
    row?: number;
    col?: number;
    u?: number;
  };
}

const DEFAULT_WIDTHS = { serial: 160, layout: 120, row: 72, col: 72, u: 86 };

/**
 * 返回 [序列号, 机箱行×列?, 节点行号/列号?, 非节点U位?, 状态] 列。
 * 设备名称列由调用方在工厂结果前自行插入（宽度不同）。
 */
export function buildCommonBatchColumns({
  updateRow,
  genNodeName,
  isChassis,
  isNode,
  widths
}: CommonColumnDeps): BatchColumns {
  const w = { ...DEFAULT_WIDTHS, ...widths };
  const columns: BatchColumns = [
    {
      title: '序列号',
      dataIndex: 'serial_number',
      width: w.serial,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateRow(record.key, 'serial_number', e.target.value)}
          placeholder="序列号"
        />
      )
    }
  ];

  if (isChassis) {
    columns.push({
      title: '行×列',
      key: 'node_layout',
      width: w.layout,
      render: (_value, record) => (
        <span style={{ display: 'inline-flex', gap: 4 }}>
          <InputNumber
            size="small"
            value={record.node_rows ?? 2}
            min={1}
            max={16}
            style={{ width: 48 }}
            onChange={(v) => updateRow(record.key, 'node_rows', v ?? 2)}
          />
          <span>×</span>
          <InputNumber
            size="small"
            value={record.node_cols ?? 2}
            min={1}
            max={16}
            style={{ width: 48 }}
            onChange={(v) => updateRow(record.key, 'node_cols', v ?? 2)}
          />
        </span>
      )
    });
  }

  if (isNode) {
    columns.push(
      {
        title: '行号',
        key: 'node_row',
        width: w.row,
        render: (_value, record) => (
          <InputNumber
            size="small"
            value={record.node_row}
            min={1}
            max={16}
            style={{ width: '100%' }}
            onChange={(v) => {
              const row = v ?? undefined;
              updateRow(record.key, 'node_row', row);
              const name = genNodeName(row, record.node_col);
              if (name) updateRow(record.key, 'device_name', name);
            }}
            placeholder="行"
          />
        )
      },
      {
        title: '列号',
        key: 'node_col',
        width: w.col,
        render: (_value, record) => (
          <InputNumber
            size="small"
            value={record.node_col}
            min={1}
            max={16}
            style={{ width: '100%' }}
            onChange={(v) => {
              const col = v ?? undefined;
              updateRow(record.key, 'node_col', col);
              const name = genNodeName(record.node_row, col);
              if (name) updateRow(record.key, 'device_name', name);
            }}
            placeholder="列"
          />
        )
      }
    );
  }

  if (!isNode) {
    columns.push({
      title: 'U位',
      dataIndex: 'u_position',
      width: w.u,
      render: (value, record) => (
        <InputNumber
          size="small"
          value={value}
          min={1}
          max={42}
          style={{ width: '100%' }}
          placeholder="U位"
          onChange={(val) => updateRow(record.key, 'u_position', val)}
        />
      )
    });
  }

  return columns;
}
