import type { ReactNode } from 'react';
import type { TablePaginationConfig } from 'antd';
import i18n from '@/i18n';

export const MAX_OFFSET = 10_000;

export const OFFSET_LIMIT_HINT_KEY = 'pagination.offsetLimitHint';

export function isBeyondOffsetLimit(total: number | undefined): boolean {
  return typeof total === 'number' && total > MAX_OFFSET;
}

export interface ServerPaginationInput {
  current: number | undefined;
  pageSize: number | undefined;
  total: number | undefined;
  onChange?: (page: number, pageSize: number) => void;
  showSizeChanger?: boolean;
  showTotal?: boolean | ((total: number) => ReactNode);
}

function formatTotal(total: number): string {
  return i18n.t('pagination.total', { count: total });
}

export function formatLimitHint(): string {
  return i18n.t(OFFSET_LIMIT_HINT_KEY);
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
  const showTotalFn =
    typeof showTotal === 'function'
      ? showTotal
      : showTotal
        ? beyondLimit
          ? formatLimitHint
          : formatTotal
        : null;
  return {
    current,
    pageSize,
    total,
    showSizeChanger,
    ...(showTotalFn ? { showTotal: showTotalFn } : {}),
    ...(onChange ? { onChange } : {})
  };
}
