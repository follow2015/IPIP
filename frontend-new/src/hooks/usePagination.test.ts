import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePagination } from './usePagination';

describe('usePagination', () => {
  it('默认初始状态', () => {
    const { result } = renderHook(() => usePagination());
    expect(result.current.page).toBe(1);
    expect(result.current.perPage).toBe(20);
    expect(result.current.total).toBe(0);
    expect(result.current.totalPages).toBe(1);
  });

  it('自定义 initialPerPage', () => {
    const { result } = renderHook(() => usePagination(50));
    expect(result.current.perPage).toBe(50);
  });

  it('setPage 更新页码', () => {
    const { result } = renderHook(() => usePagination());
    act(() => result.current.setPage(3));
    expect(result.current.page).toBe(3);
  });

  it('setPerPage 更新每页并重置到第 1 页', () => {
    const { result } = renderHook(() => usePagination());
    act(() => result.current.setPage(5));
    act(() => result.current.setPerPage(50));
    expect(result.current.perPage).toBe(50);
    expect(result.current.page).toBe(1);
  });

  it('setTotal 影响 totalPages', () => {
    const { result } = renderHook(() => usePagination(10));
    act(() => result.current.setTotal(95));
    expect(result.current.total).toBe(95);
    expect(result.current.totalPages).toBe(10);
  });

  it('reset 回到初始', () => {
    const { result } = renderHook(() => usePagination(10));
    act(() => {
      result.current.setPage(3);
      result.current.setPerPage(50);
      result.current.setTotal(100);
    });
    act(() => result.current.reset());
    expect(result.current.page).toBe(1);
    expect(result.current.perPage).toBe(10);
    expect(result.current.total).toBe(0);
  });
});
