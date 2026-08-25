/**
 * 分页 Hook
 * - 管理页码/每页数/总数状态
 */
import { useState, useCallback } from 'react';
import type { PaginationParams } from '@/types/api';

interface UsePaginationReturn {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
  setPage: (page: number) => void;
  setPerPage: (perPage: number) => void;
  setTotal: (total: number) => void;
  reset: () => void;
  paginationParams: PaginationParams;
}

const DEFAULT_PER_PAGE = 20;

export function usePagination(
  initialPerPage: number = DEFAULT_PER_PAGE,
): UsePaginationReturn {
  const [page, setPage] = useState(1);
  const [perPage, setPerPageState] = useState(initialPerPage);
  const [total, setTotal] = useState(0);

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const setPerPage = useCallback((size: number) => {
    setPerPageState(size);
    setPage(1);
  }, []);

  const reset = useCallback(() => {
    setPage(1);
    setPerPageState(initialPerPage);
    setTotal(0);
  }, [initialPerPage]);

  const paginationParams: PaginationParams = { page, per_page: perPage };

  return {
    page,
    perPage,
    total,
    totalPages,
    setPage,
    setPerPage,
    setTotal,
    reset,
    paginationParams,
  };
}
