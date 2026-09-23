import { useCallback, useMemo, useState } from 'react';
import type { Key } from 'react';
import type { TableProps } from 'antd';
import type { TFunction } from 'i18next';

export interface UseBatchSelectionOptions<T> {
  getRowKey?: (record: T) => Key;
  preserveSelectedRowKeys?: boolean;
  dataSource?: T[];
}

export interface UseBatchSelectionReturn<T> {
  selectedKeys: Key[];
  setSelectedKeys: (keys: Key[]) => void;
  count: number;
  completeSelectedRows: T[] | null;
  unresolvedSelectedCount: number;
  isSelectionFullyResolved: boolean;
  hasSelection: boolean;
  rowSelection: TableProps<T>['rowSelection'];
  clear: () => void;
  allCurrentPageSelected: boolean;
  toggleSelectAllOnPage: (rows: T[]) => void;
}

export function scopeViolationMessage<T>(
  t: TFunction<'device'>,
  batch: Pick<UseBatchSelectionReturn<T>, 'unresolvedSelectedCount'>,
  actionLabel: string,
  unit = t('batch.unit')
): string {
  return t('batch.crossPageWarning', {
    action: actionLabel,
    count: batch.unresolvedSelectedCount,
    unit
  });
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

  const pageSelectedRows = useMemo(() => {
    if (!dataSource) return [];
    return dataSource.filter((r) => keySet.has(String(getRowKey(r))));
  }, [dataSource, keySet, getRowKey]);

  const count = selectedKeys.length;
  const unresolvedSelectedCount = count - pageSelectedRows.length;
  const isSelectionFullyResolved = unresolvedSelectedCount === 0;

  const completeSelectedRows = isSelectionFullyResolved ? pageSelectedRows : null;

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
    count,
    completeSelectedRows,
    unresolvedSelectedCount,
    isSelectionFullyResolved,
    hasSelection,
    rowSelection,
    clear,
    allCurrentPageSelected,
    toggleSelectAllOnPage
  };
}
