import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBatchSelection } from '@/hooks/useBatchSelection';

interface Row {
  id: number;
  name: string;
}

const rows: Row[] = [
  { id: 1, name: 'a' },
  { id: 2, name: 'b' },
  { id: 3, name: 'c' }
];

describe('useBatchSelection', () => {
  it('初始化为空', () => {
    const { result } = renderHook(() => useBatchSelection<Row>());
    expect(result.current.selectedKeys).toEqual([]);
    expect(result.current.count).toBe(0);
    expect(result.current.hasSelection).toBe(false);
    expect(result.current.selectedRows).toEqual([]);
  });

  it('选择行后派生 selectedRows，且 key 归一化为 string', () => {
    const { result } = renderHook(() =>
      useBatchSelection<Row>({ dataSource: rows, getRowKey: (r) => r.id })
    );
    act(() => result.current.setSelectedKeys([1, 3]));
    expect(result.current.selectedKeys).toEqual(['1', '3']);
    expect(result.current.count).toBe(2);
    expect(result.current.hasSelection).toBe(true);
    expect(result.current.selectedRows.map((r) => r.name)).toEqual(['a', 'c']);
  });

  it('rowSelection.preserveSelectedRowKeys 默认 true', () => {
    const { result } = renderHook(() => useBatchSelection<Row>());
    expect(result.current.rowSelection?.preserveSelectedRowKeys).toBe(true);
  });

  it('clear 清空选择并清空派生行', () => {
    const { result } = renderHook(() =>
      useBatchSelection<Row>({ dataSource: rows, getRowKey: (r) => r.id })
    );
    act(() => result.current.setSelectedKeys([2]));
    expect(result.current.count).toBe(1);
    act(() => result.current.clear());
    expect(result.current.count).toBe(0);
    expect(result.current.selectedRows).toEqual([]);
  });

  it('rowSelection.onChange 透传并归一化', () => {
    const { result } = renderHook(() => useBatchSelection<Row>());
    act(() => result.current.rowSelection?.onChange?.([5, 6], [], { type: 'all' }));
    expect(result.current.selectedKeys).toEqual(['5', '6']);
  });

  it('toggleSelectAllOnPage 全选 / 取消当前页', () => {
    const { result } = renderHook(() =>
      useBatchSelection<Row>({ dataSource: rows, getRowKey: (r) => r.id })
    );
    expect(result.current.allCurrentPageSelected).toBe(false);
    act(() => result.current.toggleSelectAllOnPage(rows));
    expect(result.current.allCurrentPageSelected).toBe(true);
    expect(result.current.selectedKeys).toEqual(['1', '2', '3']);
    act(() => result.current.toggleSelectAllOnPage(rows));
    expect(result.current.allCurrentPageSelected).toBe(false);
    expect(result.current.selectedKeys).toEqual([]);
  });

  it('未提供 dataSource 时 selectedRows 为空', () => {
    const { result } = renderHook(() => useBatchSelection<Row>({ getRowKey: (r) => r.id }));
    act(() => result.current.setSelectedKeys([1]));
    expect(result.current.selectedRows).toEqual([]);
  });
});
