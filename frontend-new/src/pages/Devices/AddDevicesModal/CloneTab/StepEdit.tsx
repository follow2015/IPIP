import { Button, Space, Table, Alert } from 'antd';
import { ThunderboltOutlined, AimOutlined } from '@ant-design/icons';
import type { DeviceBatchRow } from '../shared';
import type { BatchColumns } from '../batchColumns';

export interface StepEditProps {
  diffRows: DeviceBatchRow[];
  diffColumns: BatchColumns;
  isNodeTemplate: boolean;
  effectiveCabinetId: number;
  handleAutoAssignU: () => void;
  handleRegenerateNames: () => void;
  availableUPositions: unknown;
  availableUCount: number;
  cloneChassisId: number | undefined;
  cloneAvailablePositions: number[];
}

const StepEdit: React.FC<StepEditProps> = ({
  diffRows,
  diffColumns,
  isNodeTemplate,
  effectiveCabinetId,
  handleAutoAssignU,
  handleRegenerateNames,
  availableUPositions,
  availableUCount,
  cloneChassisId,
  cloneAvailablePositions
}) => (
  <div>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
      <Space>
        {!isNodeTemplate && (
          <Button
            size="small"
            icon={<AimOutlined />}
            disabled={!effectiveCabinetId}
            onClick={handleAutoAssignU}
          >
            自动分配U位
          </Button>
        )}
        <Button size="small" icon={<ThunderboltOutlined />} onClick={handleRegenerateNames}>
          重生成名称
        </Button>
      </Space>
      <Space>
        <span style={{ color: '#8c8c8c', fontSize: 12 }}>共 {diffRows.length} 台</span>
        {!isNodeTemplate && availableUPositions != null && (
          <span style={{ color: '#8c8c8c', fontSize: 12 }}>可用U位：{availableUCount} 个</span>
        )}
        {isNodeTemplate && cloneChassisId && (
          <span style={{ color: '#8c8c8c', fontSize: 12 }}>
            机箱空余：{cloneAvailablePositions.length} 个
          </span>
        )}
      </Space>
    </div>
    <Table
      columns={diffColumns}
      dataSource={diffRows}
      rowKey="key"
      size="small"
      pagination={false}
      scroll={{ y: 300 }}
    />
    {!isNodeTemplate && !effectiveCabinetId && (
      <Alert
        type="info"
        title="未选择机柜时 U 位不会保存，可在上一步选择目标机柜。"
        showIcon
        style={{ marginTop: 12 }}
      />
    )}
  </div>
);

export default StepEdit;
