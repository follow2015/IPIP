import { Button, Space, Table, Alert } from 'antd';
import { ThunderboltOutlined, AimOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
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
}) => {
  const { t } = useTranslation('device');
  return (
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
              {t('form.location.uPosition.autoAssignTooltip')}
            </Button>
          )}
          <Button size="small" icon={<ThunderboltOutlined />} onClick={handleRegenerateNames}>
            {t('addModal.action.regenerateNames')}
          </Button>
        </Space>
        <Space>
          <span style={{ color: '#8c8c8c', fontSize: 12 }}>
            {t('addModal.clone.totalCount', { count: diffRows.length })}
          </span>
          {!isNodeTemplate && availableUPositions != null && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {t('form.location.availableUPositions', { count: availableUCount })}
            </span>
          )}
          {isNodeTemplate && cloneChassisId && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {t('addModal.clone.chassisVacant', { count: cloneAvailablePositions.length })}
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
          title={t('addModal.clone.noCabinetHint')}
          showIcon
          style={{ marginTop: 12 }}
        />
      )}
    </div>
  );
};

export default StepEdit;
