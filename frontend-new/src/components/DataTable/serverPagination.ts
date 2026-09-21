import type { TablePaginationConfig } from 'antd';

export const MAX_OFFSET = 10_000;

export const OFFSET_LIMIT_HINT = '结果过多，请用筛选缩小范围';

export function isBeyondOffsetLimit(total: number | undefined): boolean {
  return typeof total === 'number' && total > MAX_OFFSET;
}

export interface ServerPaginationInput {
  current: number | undefined;
  pageSize: number | undefined;
  total: number | undefined;
  onChange?: (page: number, pageSize: number) => void;
  showSizeChanger?: boolean;
  showTotal?: boolean;
}

function formatTotal(total: number): string {
  return `共 ${total} 条`;
}

export function formatLimitHint(): string {
  return OFFSET_LIMIT_HINT;
}

export function serverPagination({
  current,
  pageSize,
  total,
  onChange,
  showSizeChanger = true,
  showTotal = true
}: ServerPaginationInput): TablePaginationConfig {
  const beyondLimit = isBeyondOffsetLimit(total);
  return {
    current,
    pageSize,
    total,
    showSizeChanger,
    ...(showTotal ? { showTotal: beyondLimit ? formatLimitHint : formatTotal } : {}),
    ...(onChange ? { onChange } : {})
  };
}
