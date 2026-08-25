/**
 * PortTable — 端口表格（SSH / 手动模式共用）
 * 仅负责渲染，列定义与数据由上游注入，便于两模式复用。
 */
import { memo } from 'react';
import { Table } from 'antd';
import type { TableProps } from 'antd';
import type { SwitchPort } from '@/types/models';

interface PortTableProps {
  columns: TableProps<SwitchPort>['columns'];
  dataSource: SwitchPort[];
  loading: boolean;
  rowSelection?: TableProps<SwitchPort>['rowSelection'];
  highlightPort: string | null;
}

export const PortTable = memo<PortTableProps>(
  ({ columns, dataSource, loading, rowSelection, highlightPort }) => (
    <Table
      columns={columns}
      dataSource={dataSource}
      rowKey="port_name"
      loading={loading}
      size="small"
      pagination={false}
      rowSelection={rowSelection}
      rowClassName={(record) =>
        record.port_name === highlightPort ? 'ant-table-row-selected' : ''
      }
    />
  )
);
