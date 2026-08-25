/**
 * BatchDeviceTable — 批量添加的行编辑表格
 *
 * 动态列：机箱模式显示「行×列」；节点模式显示「行号/列号」并隐藏 U 位/U 高；
 * 非节点模式显示 U 位/U 高。节点模式的行号/列号变更会联动重命名设备。
 */

import React from 'react';
import { Table, Input, InputNumber, Select, Button, Space } from 'antd';
import { CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import { STATUS_OPTIONS } from '../shared';
import type { DeviceBatchRow } from '../shared';
import type { EditableRowsApi } from './useBatchAddTab';
import { buildCommonBatchColumns, type BatchColumns } from '../batchColumns';

interface BatchDeviceTableProps {
  rows: DeviceBatchRow[];
  isChassisMode: boolean;
  isNodeMode: boolean;
  updateRow: EditableRowsApi<DeviceBatchRow>['updateRow'];
  copyRow: (key: string, overrides?: Partial<DeviceBatchRow>) => void;
  deleteRow: (key: string) => void;
  genNodeName: (nodeRow?: number, nodeCol?: number) => string;
}

const BatchDeviceTable: React.FC<BatchDeviceTableProps> = ({
  rows,
  isChassisMode,
  isNodeMode,
  updateRow,
  copyRow,
  deleteRow,
  genNodeName
}) => {
  const columns: BatchColumns = [
    { title: '#', width: 44, render: (_value, _record, index) => index + 1 },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      width: 200,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateRow(record.key, 'device_name', e.target.value)}
          placeholder="设备名称"
        />
      )
    },
    {
      title: '型号',
      dataIndex: 'device_model',
      width: 140,
      render: (value, record) => (
        <Input
          size="small"
          value={value}
          onChange={(e) => updateRow(record.key, 'device_model', e.target.value)}
          placeholder="型号"
        />
      )
    },
    ...buildCommonBatchColumns({
      updateRow,
      genNodeName,
      isChassis: isChassisMode,
      isNode: isNodeMode
    }),
    {
      title: 'U高',
      dataIndex: 'height_u',
      width: 72,
      render: (value, record) => (
        <InputNumber
          size="small"
          value={value}
          min={1}
          max={42}
          style={{ width: '100%' }}
          onChange={(val) => updateRow(record.key, 'height_u', val ?? 1)}
        />
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value, record) => (
        <Select
          size="small"
          value={value}
          options={STATUS_OPTIONS}
          style={{ width: '100%' }}
          onChange={(val) => updateRow(record.key, 'status', val)}
        />
      )
    },
    {
      title: '操作',
      width: 76,
      render: (_value, record) => (
        <Space size={4}>
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            title="复制行"
            onClick={() => copyRow(record.key, { serial_number: '' })}
          />
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            title="删除行"
            disabled={rows.length <= 1}
            onClick={() => deleteRow(record.key)}
          />
        </Space>
      )
    }
  ];

  return (
    <Table
      columns={columns}
      dataSource={rows}
      rowKey="key"
      size="small"
      pagination={false}
      scroll={{ y: 320 }}
    />
  );
};

export default BatchDeviceTable;
