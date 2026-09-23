import React from 'react';
import { Modal, Table, Space, Button, Alert, Typography } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExportOutlined,
  RedoOutlined
} from '@ant-design/icons';
import type { BatchCreateResult, BatchCreateItemResult } from '@/types/models';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface BatchResultModalProps {
  open: boolean;
  onClose: () => void;
  result: BatchCreateResult | null;
  title?: string;
  onRetry?: (failedItems: BatchCreateItemResult[]) => void;
}

const BatchResultModal: React.FC<BatchResultModalProps> = ({
  open,
  onClose,
  result,
  title,
  onRetry
}) => {
  const { t } = useTranslation('device');

  if (!result) return null;

  const modalTitle = title ?? t('batchResult.title');
  const failedItems = result.results.filter((r) => !r.success);
  const hasFailures = failedItems.length > 0;

  const handleExportFailed = () => {
    const headers = [t('batchResult.column.index'), t('field.name'), t('batchResult.column.reason')];
    const rows = failedItems.map((item) => [
      item.index + 1,
      item.device_name,
      item.error || t('batchResult.unknownError')
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'batch_failed_records.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns = [
    {
      title: t('batchResult.column.index'),
      dataIndex: 'index',
      key: 'index',
      render: (i: number) => i + 1,
      width: 60
    },
    { title: t('field.name'), dataIndex: 'device_name', key: 'device_name' },
    {
      title: t('batchResult.column.reason'),
      dataIndex: 'error',
      key: 'error',
      render: (text: string) => <Text type="danger">{text}</Text>
    }
  ];

  return (
    <Modal open={open} title={modalTitle} onCancel={onClose} footer={null} width={600}>
      <Alert
        type={hasFailures ? 'warning' : 'success'}
        showIcon
        icon={hasFailures ? <CloseCircleOutlined /> : <CheckCircleOutlined />}
        title={
          <Space size="large">
            <Text>
              {t('batchResult.summary.success')}{' '}
              <Text strong type="success">
                {result.success_count}
              </Text>{' '}
              {t('batchResult.summary.unit', { count: result.success_count })}
            </Text>
            {hasFailures && (
              <Text>
                {t('batchResult.summary.failed')}{' '}
                <Text strong type="danger">
                  {result.failed_count}
                </Text>{' '}
                {t('batchResult.summary.unit', { count: result.failed_count })}
              </Text>
            )}
          </Space>
        }
        style={{ marginBottom: 16 }}
      />
      {hasFailures && (
        <>
          <Table
            columns={columns}
            dataSource={failedItems}
            rowKey="index"
            size="small"
            pagination={false}
            style={{ marginBottom: 16 }}
            scroll={{ x: 'max-content' }}
          />
          <Space>
            <Button icon={<ExportOutlined />} onClick={handleExportFailed}>
              {t('batchResult.exportFailed')}
            </Button>
            {onRetry && (
              <Button icon={<RedoOutlined />} onClick={() => onRetry(failedItems)}>
                {t('batchResult.retryFailed')}
              </Button>
            )}
          </Space>
        </>
      )}
    </Modal>
  );
};

export default BatchResultModal;
