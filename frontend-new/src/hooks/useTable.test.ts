import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTable } from './useTable';

describe('useTable', () => {
  it('默认初始状态', () => {
    const { result } = renderHook(() => useTable());
    expect(result.current.page).toBe(1);
    expect(result.current.perPage).toBe(20);
    expect(result.current.search).toBe('');
    expect(result.current.sortBy).toBe('');
    expect(result.current.sortOrder).toBe('asc');
    expect(result.current.filters).toEqual({});
  });

  it('兼容 useTable(20) 数字入参', () => {
    const { result } = renderHook(() => useTable(50));
    expect(result.current.perPage).toBe(50);
  });

  it('setSearch 重置到第 1 页', () => {
    const { result } = renderHook(() => useTable());
    act(() => result.current.setPage(3));
    act(() => result.current.setSearch('abc'));
    expect(result.current.search).toBe('abc');
    expect(result.current.page).toBe(1);
  });

  it('setSort 重置到第 1 页', () => {
    const { result } = renderHook(() => useTable());
    act(() => result.current.setPage(3));
    act(() => result.current.setSort('name', 'desc'));
    expect(result.current.sortBy).toBe('name');
    expect(result.current.sortOrder).toBe('desc');
    expect(result.current.page).toBe(1);
  });

  it('setFilters 重置到第 1 页', () => {
    const { result } = renderHook(() => useTable());
    act(() => result.current.setPage(3));
    act(() => result.current.setFilters({ room_id: '5' }));
    expect(result.current.filters).toEqual({ room_id: '5' });
    expect(result.current.page).toBe(1);
  });

  it('updateFilter 设值转字符串、undefined 删除', () => {
    const { result } = renderHook(() => useTable());
    act(() => result.current.updateFilter('room_id', 5));
    expect(result.current.filters).toEqual({ room_id: '5' });
    act(() => result.current.updateFilter('room_id', undefined));
    expect(result.current.filters).toEqual({});
  });

  it('updateFilter 联动重置关联字段', () => {
    const { result } = renderHook(() => useTable({ filterResets: { room_id: ['cabinet_id'] } }));
    act(() => result.current.updateFilter('room_id', 1));
    act(() => result.current.updateFilter('cabinet_id', 2));
    expect(result.current.filters).toEqual({ room_id: '1', cabinet_id: '2' });
    act(() => result.current.updateFilter('room_id', 3));
    expect(result.current.filters).toEqual({ room_id: '3' });
  });

  it('reset 清空全部状态', () => {
    const { result } = renderHook(() => useTable());
    act(() => {
      result.current.setSearch('x');
      result.current.setSort('n', 'desc');
      result.current.updateFilter('r', 1);
    });
    act(() => result.current.reset());
    expect(result.current.search).toBe('');
    expect(result.current.sortBy).toBe('');
    expect(result.current.sortOrder).toBe('asc');
    expect(result.current.filters).toEqual({});
  });

  it('tableParams 空字段映射为 undefined', () => {
    const { result } = renderHook(() => useTable());
    expect(result.current.tableParams).toEqual({
      page: 1,
      per_page: 20,
      search: undefined,
      sort_by: undefined,
      sort_order: undefined,
      filters: undefined
    });
    act(() => {
      result.current.setSearch('x');
      result.current.setSort('n', 'desc');
      result.current.updateFilter('r', 1);
    });
    expect(result.current.tableParams).toEqual({
      page: 1,
      per_page: 20,
      search: 'x',
      sort_by: 'n',
      sort_order: 'desc',
      filters: { r: '1' }
    });
  });
});
