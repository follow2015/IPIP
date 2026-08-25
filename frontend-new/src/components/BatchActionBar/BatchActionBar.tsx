/**
 * BatchActionBar — 批量操作浮条
 *
 * 列表页勾选行后浮出的操作栏，统一展示「已选 N 项」+ 操作按钮插槽 + 取消选择。
 * 替换各页面手写的 Alert 工具栏（如 Devices/index.tsx 的 30 行 Alert 段落）。
 *
 * 用法：
 * ```tsx
 * <BatchActionBar count={batch.count} unit="台设备" onClear={batch.clear}>
 *   <Button danger onClick={handleBatchDelete}>批量删除</Button>
 *   <Button onClick={handleBatchStatus}>批量变更状态</Button>
 * </BatchActionBar>
 * ```
 */
import { Alert, Button, Space } from 'antd';
import { CloseCircleOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';

export interface BatchActionBarProps {
  count: number;
  unit?: string;
  onClear: () => void;
  children?: ReactNode;
  className?: string;
}

export function BatchActionBar({
  count,
  unit = '项',
  onClear,
  children,
  className
}: BatchActionBarProps) {
  if (count === 0) return null;

  return (
    <Alert
      type="info"
      showIcon
      className={className}
      style={{ marginBottom: 16 }}
      title={
        <Space wrap>
          <span>
            已选择 <strong>{count}</strong> {unit}
          </span>
          {children}
          <Button size="small" type="link" icon={<CloseCircleOutlined />} onClick={onClear}>
            取消选择
          </Button>
        </Space>
      }
    />
  );
}

export default BatchActionBar;
