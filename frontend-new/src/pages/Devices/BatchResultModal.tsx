import React from 'react';
import { Modal, Table, Space, Button, Alert, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ExportOutlined, RedoOutlined } from '@ant-design/icons';
import type { BatchCreateResult, BatchCreateItemResult } from '@/types/models';

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
  title = '批量操作结果',
  onRetry,
}) => {
  if (!result) return null;

  const failedItems = result.results.filter((r) => !r.success);
  const hasFailures = failedItems.length > 0;

  
  const handleExportFailed = () => {
    const headers = ['序号', '设备名称', '失败原因'];
    const rows = failedItems.map((item) => [item.index + 1, item.device_name, item.error || '未知错误']);
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
    { title: '序号', dataIndex: 'index', key: 'index', render: (i: number) => i + 1, width: 60 },
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name' },
    { title: '失败原因', dataIndex: 'error', key: 'error', render: (text: string) => <Text type="danger">{text}</Text> },
  ];

  return (
    <Modal open={open} title={title} onCancel={onClose} footer={null} width={600}>
      <Alert
        type={hasFailures ? 'warning' : 'success'}
        showIcon
        icon={hasFailures ? <CloseCircleOutlined /> : <CheckCircleOutlined />}
        title={
          <Space size="large">
            <Text>成功: <Text strong type="success">{result.success_count}</Text> 台</Text>
            {hasFailures && <Text>失败: <Text strong type="danger">{result.failed_count}</Text> 台</Text>}
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
          />
          <Space>
            <Button icon={<ExportOutlined />} onClick={handleExportFailed}>导出失败记录</Button>
            {onRetry && (
              <Button icon={<RedoOutlined />} onClick={() => onRetry(failedItems)}>重试失败项</Button>
            )}
          </Space>
        </>
      )}
    </Modal>
  );
};

export default BatchResultModal;
