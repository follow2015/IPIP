import { confirm } from '@/utils/confirm';

import { useState, useCallback } from 'react';

import { useTable, type UseTableReturn } from './useTable';
import { useMessage } from './useMessage';
import type { PaginatedData, PaginationParams } from '@/types/api';
import type { UseMutationResult } from '@tanstack/react-query';
import type { ApiResponse } from '@/types/api';


type TableParams = UseTableReturn['tableParams'];


export interface UseCrudPageOptions<
  T extends { id: number },
  TListParams extends object = PaginationParams
> {
  
  useList: (params?: TListParams) => {
    data?: PaginatedData<T>;
    isLoading: boolean;
    refetch: () => void;
  };
  
  useDelete: () => UseMutationResult<ApiResponse<unknown>, Error, number>;
  
  nameKey: keyof T;
  
  nameLabel: string;
  
  buildListParams?: (tp: TableParams) => TListParams;
}


export interface UseCrudPageReturn<T extends { id: number }> {
  
  table: UseTableReturn;
  
  data: PaginatedData<T> | undefined;
  
  isLoading: boolean;
  
  refetch: () => void;
  
  formOpen: boolean;
  
  editRecord: T | null;
  
  handleAdd: () => void;
  
  handleEdit: (record: T) => void;
  
  handleDelete: (record: T) => void;
  
  closeForm: () => void;
}


export function useCrudPage<
  T extends { id: number },
  TListParams extends object = PaginationParams
>(options: UseCrudPageOptions<T, TListParams>): UseCrudPageReturn<T> {
  const { useList, useDelete, nameKey, nameLabel, buildListParams } = options;

  const table = useTable();
  const [formOpen, setFormOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<T | null>(null);
  const deleteMutation = useDelete();
  const message = useMessage();

  const listParams: TListParams = buildListParams
    ? buildListParams(table.tableParams)
    : (table.tableParams as unknown as TListParams);
  const { data, isLoading, refetch } = useList(listParams);

  
  const handleAdd = useCallback(() => {
    setEditRecord(null);
    setFormOpen(true);
  }, []);

  
  const handleEdit = useCallback((record: T) => {
    setEditRecord(record);
    setFormOpen(true);
  }, []);

  
  const handleDelete = useCallback(
    (record: T) => {
      const displayName = String(record[nameKey] ?? '');
      confirm({
        title: '确认删除',
        content: `确定要删除${nameLabel}「${displayName}」吗？`,
        okText: '确定',
        cancelText: '取消',
        onOk: async () => {
          try {
            await deleteMutation.mutateAsync(record.id);
            message.success('删除成功');
            refetch();
          } catch (err) {
            message.error(err instanceof Error ? err.message : '删除失败');
          }
        }
      });
    },
    [deleteMutation, nameKey, nameLabel, message, refetch]
  );

  
  const closeForm = useCallback(() => {
    setFormOpen(false);
    setEditRecord(null);
    refetch();
  }, [refetch]);

  return {
    table,
    data,
    isLoading,
    refetch,
    formOpen,
    editRecord,
    handleAdd,
    handleEdit,
    handleDelete,
    closeForm
  };
}
