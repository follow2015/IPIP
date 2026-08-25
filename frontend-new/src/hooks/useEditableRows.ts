/**
 * useEditableRows — 通用行编辑 Hook
 *
 * 解决原有架构问题：
 *   ① 原 `let rowKeyCounter = 0` 为模块级可变状态，所有弹窗共享同一计数器，
 *      组件卸载不会重置，多实例并发时可能生成重复 key。
 *      本 Hook 使用 useRef 将计数器限定在组件生命周期内，完全隔离。
 *   ② 原 handleAddRow / handleDeleteRow / handleCopyRow / handleUpdateRow
 *      在 BatchAddDeviceModal 和 QuickCloneDeviceModal 中逐字复制。
 *      本 Hook 将这些操作收拢为一套实现，两处复用。
 *
 * 用法：
 *   const { rows, addRow, deleteRow, copyRow, updateRow, resetRows } =
 *     useEditableRows<BatchRow>();
 */
import { useState, useCallback, useRef } from 'react';


export interface EditableRow {
  key: string;
}


export function useEditableRows<T extends EditableRow>(initialRows: T[] = []) {
  
  const counterRef = useRef(0);

  
  const makeKey = useCallback((): string => {
    counterRef.current += 1;
    
    return `row-${Date.now()}-${counterRef.current}`;
  }, []);

  const [rows, setRows] = useState<T[]>(initialRows);

  
  const addRow = useCallback(
    (rowData: Omit<T, 'key'>): void => {
      setRows(prev => [...prev, { ...rowData, key: makeKey() } as T]);
    },
    [makeKey],
  );

  
  const addRows = useCallback(
    (rowsData: Omit<T, 'key'>[]): void => {
      setRows(prev => [
        ...prev,
        ...rowsData.map(r => ({ ...r, key: makeKey() } as T)),
      ]);
    },
    [makeKey],
  );

  
  const deleteRow = useCallback((key: string): void => {
    setRows(prev => prev.filter(r => r.key !== key));
  }, []);

  
  const copyRow = useCallback(
    (key: string, overrides: Partial<Omit<T, 'key'>> = {}): void => {
      setRows(prev => {
        const idx = prev.findIndex(r => r.key === key);
        if (idx === -1) return prev;
        const copy = { ...prev[idx], key: makeKey(), ...overrides } as T;
        const next = [...prev];
        next.splice(idx + 1, 0, copy);
        return next;
      });
    },
    [makeKey],
  );

  
  const updateRow = useCallback(
    <K extends keyof T>(key: string, field: K, value: T[K]): void => {
      setRows(prev => prev.map(r => (r.key === key ? { ...r, [field]: value } : r)));
    },
    [],
  );

  
  const resetRows = useCallback(
    (newRows: Omit<T, 'key'>[]): void => {
      setRows(newRows.map(r => ({ ...r, key: makeKey() } as T)));
    },
    [makeKey],
  );

  
  const transformRows = useCallback(
    (mapper: (row: T, index: number) => Omit<T, 'key'>): void => {
      setRows(prev =>
        prev.map((row, i) => ({ ...mapper(row, i), key: row.key } as T)),
      );
    },
    [],
  );

  return {
    rows,
    
    setRows,
    addRow,
    addRows,
    deleteRow,
    copyRow,
    updateRow,
    resetRows,
    transformRows,
  };
}
