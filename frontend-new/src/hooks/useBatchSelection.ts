/**
 * useBatchSelection — 列表页批量选择统一 Hook
 *
 * 解决散落在各页面的重复模式：
 * - 各自 useState(selectedRowKeys) + 手写 rowSelection 对象
 * - rowKey 不统一（"id" / String(id) / "ip_address"）导致 selectedRowKeys 类型混乱
 * - 批量弹窗消费已选行时手写 keySet 过滤 dataSource
 * - 翻页是否保留选择各写各的
 *
 * 本 Hook 统一：
 * 1. 内部把 key 归一化为 string，消除 number/string 混用与 `as number[]` 强转隐患
 * 2. preserveSelectedRowKeys 默认 true（翻页保留已选项）
 * 3. 由 dataSource + getRowKey 自动派生 selectedRows，替换手写的 keySet 过滤
 * 4. 暴露 rowSelection 直接透传给 <Table>/<DataTable rowSelection>
 *
 * 用法：
 * ```tsx
 * const batch = useBatchSelection<Device>({
 *   dataSource: data?.items ?? [],
 *   getRowKey: (r) => String(r.id ?? ''), // 必须与表格 rowKey 完全一致
 * });
 * <DataTable rowSelection={batch.rowSelection} ... />
 * // 批量删除：batch.selectedKeys.map(Number)（内部归一化为 string，消费时需转 number）；弹窗消费：batch.selectedRows
 * ```
 */
import { useCallback, useMemo, useState } from 'react';
import type { Key } from 'react';
import type { TableProps } from 'antd';

export interface UseBatchSelectionOptions<T> {
  
  getRowKey?: (record: T) => Key;
  
  preserveSelectedRowKeys?: boolean;
  
  dataSource?: T[];
}

export interface UseBatchSelectionReturn<T> {
  
  selectedKeys: Key[];
  
  setSelectedKeys: (keys: Key[]) => void;
  
  selectedRows: T[];
  
  hasSelection: boolean;
  
  count: number;
  
  rowSelection: TableProps<T>['rowSelection'];
  
  clear: () => void;
  
  allCurrentPageSelected: boolean;
  
  toggleSelectAllOnPage: (rows: T[]) => void;
}

function defaultGetRowKey<T>(record: T): Key {
  const id = (record as unknown as { id?: Key }).id;
  return id ?? '';
}

export function useBatchSelection<T extends object>(
  options: UseBatchSelectionOptions<T> = {}
): UseBatchSelectionReturn<T> {
  const { getRowKey = defaultGetRowKey, preserveSelectedRowKeys = true, dataSource } = options;

  const [selectedKeys, setSelectedKeysState] = useState<Key[]>([]);

  
  const setSelectedKeys = useCallback((keys: Key[]) => {
    setSelectedKeysState(keys.map(String));
  }, []);

  const keySet = useMemo(() => new Set(selectedKeys.map(String)), [selectedKeys]);

  const selectedRows = useMemo(() => {
    if (!dataSource) return [];
    return dataSource.filter((r) => keySet.has(String(getRowKey(r))));
  }, [dataSource, keySet, getRowKey]);

  const count = selectedKeys.length;
  const hasSelection = count > 0;

  const rowSelection = useMemo<TableProps<T>['rowSelection']>(
    () => ({
      selectedRowKeys: selectedKeys,
      onChange: (keys) => setSelectedKeys(keys),
      preserveSelectedRowKeys
    }),
    [selectedKeys, setSelectedKeys, preserveSelectedRowKeys]
  );

  const clear = useCallback(() => setSelectedKeysState([]), []);

  const currentPageKeys = useMemo(
    () => (dataSource ?? []).map((r) => String(getRowKey(r))),
    [dataSource, getRowKey]
  );

  const allCurrentPageSelected =
    currentPageKeys.length > 0 && currentPageKeys.every((k) => keySet.has(k));

  const toggleSelectAllOnPage = useCallback(
    (rows: T[]) => {
      const pageKeys = rows.map((r) => String(getRowKey(r)));
      if (allCurrentPageSelected) {
        const pageSet = new Set(pageKeys);
        setSelectedKeysState((prev) => prev.filter((k) => !pageSet.has(String(k))));
      } else {
        const merged = new Set<string>([...selectedKeys.map(String), ...pageKeys]);
        setSelectedKeysState(Array.from(merged));
      }
    },
    [allCurrentPageSelected, selectedKeys, getRowKey]
  );

  return {
    selectedKeys,
    setSelectedKeys,
    selectedRows,
    hasSelection,
    count,
    rowSelection,
    clear,
    allCurrentPageSelected,
    toggleSelectAllOnPage
  };
}
