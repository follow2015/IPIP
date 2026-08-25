/**
 * 表格 Hook（筛选 + 排序 + 分页整合）
 *
 * 重构改动——关键 Bug 修复：
 *
 * 原代码：
 *   const setSearchWrapper = useCallback(() => { ... }, [pagination]);
 *
 * 问题：`usePagination` 每次渲染都返回一个新对象（即使内部值没变），
 * 所以 `[pagination]` 等价于 `[]`（每次渲染都不同），
 * 导致四个 useCallback 在每次渲染时都被重新创建，
 * 相当于没有 memoize，子组件 memo 完全失效。
 *
 * 修复：从 usePagination 解构出**稳定的函数引用**，直接放入 deps：
 *   useState setter（setPage）本身引用稳定
 *   usePagination 内部 useCallback 包裹的 setPerPage / reset 也是稳定的
 *
 * 同时用 useMemo 包裹 tableParams，避免每次渲染都生成新对象引起下游 Query 重复触发。
 */
import { useState, useCallback, useMemo } from 'react';
import { usePagination } from './usePagination';
import type { PaginationParams } from '@/types/api';

interface SortParams {
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}


export interface UseTableOptions {
  
  initialPerPage?: number;
  
  filterResets?: Record<string, string[]>;
}

export interface UseTableReturn {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
  search: string;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  filters: Record<string, string | string[]>;
  setPage: (page: number) => void;
  setPerPage: (perPage: number) => void;
  setTotal: (total: number) => void;
  setSearch: (search: string) => void;
  setSort: (sortBy: string, sortOrder: 'asc' | 'desc') => void;
  setFilters: (filters: Record<string, string | string[]>) => void;
  
  updateFilter: (key: string, value: string | number | boolean | undefined) => void;
  reset: () => void;
  tableParams: PaginationParams & SortParams & { search?: string; filters?: Record<string, string | string[]> };
}

export function useTable(optionsOrPerPage?: UseTableOptions | number): UseTableReturn {
  
  const options: UseTableOptions = typeof optionsOrPerPage === 'number'
    ? { initialPerPage: optionsOrPerPage }
    : (optionsOrPerPage ?? {});
  const initialPerPage = options.initialPerPage ?? 20;
  const filterResets = options.filterResets ?? {};
  const pagination = usePagination(initialPerPage);

  
  const { setPage, setPerPage, setTotal, reset: resetPagination } = pagination;

  const [search,    setSearchRaw]  = useState('');
  const [sortBy,    setSortBy]     = useState('');
  const [sortOrder, setSortOrder]  = useState<'asc' | 'desc'>('asc');
  const [filters,   setFiltersRaw] = useState<Record<string, string | string[]>>({});

  
  const setSearch = useCallback(
    (value: string) => {
      setSearchRaw(value);
      setPage(1);
    },
    [setPage], 
  );

  
  const setSort = useCallback(
    (field: string, order: 'asc' | 'desc') => {
      setSortBy(field);
      setSortOrder(order);
      setPage(1);
    },
    [setPage],
  );

  
  const setFilters = useCallback(
    (newFilters: Record<string, string | string[]>) => {
      setFiltersRaw(newFilters);
      setPage(1);
    },
    [setPage],
  );

  
  const updateFilter = useCallback(
    (key: string, value: string | number | boolean | undefined) => {
      const resets = filterResets[key] ?? [];
      const newFilters = { ...filters };
      if (value === undefined) {
        delete newFilters[key];
      } else {
        newFilters[key] = String(value);
      }
      
      for (const resetKey of resets) {
        delete newFilters[resetKey];
      }
      setFiltersRaw(newFilters);
      setPage(1);
    },
    [filters, filterResets, setPage],
  );

  
  const reset = useCallback(() => {
    resetPagination(); 
    setSearchRaw('');
    setSortBy('');
    setSortOrder('asc');
    setFiltersRaw({});
  }, [resetPagination]);

  
  const tableParams = useMemo(
    () => ({
      page:       pagination.page,
      per_page:   pagination.perPage,
      search:     search    || undefined,
      sort_by:    sortBy    || undefined,
      sort_order: sortBy    ? sortOrder : undefined,
      filters:    Object.keys(filters).length > 0 ? filters : undefined,
    }),
    
    [pagination.page, pagination.perPage, search, sortBy, sortOrder, filters],
  );

  return {
    page:       pagination.page,
    perPage:    pagination.perPage,
    total:      pagination.total,
    totalPages: pagination.totalPages,
    search,
    sortBy,
    sortOrder,
    filters,
    setPage,
    setPerPage,
    setTotal,
    setSearch,
    setSort,
    setFilters,
    updateFilter,
    reset,
    tableParams,
  };
}
