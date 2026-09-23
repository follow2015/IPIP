import { useConfirm } from '@/utils/confirm';
import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useDisclosure } from './useDisclosure';
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
  const { t } = useTranslation();
  const confirm = useConfirm();
  const { useList, useDelete, nameKey, nameLabel, buildListParams } = options;

  const table = useTable();
  const form = useDisclosure();
  const [editRecord, setEditRecord] = useState<T | null>(null);
  const deleteMutation = useDelete();
  const message = useMessage();

  const listParams: TListParams = buildListParams
    ? buildListParams(table.tableParams)
    : (table.tableParams as unknown as TListParams);
  const { data, isLoading, refetch } = useList(listParams);

  const handleAdd = useCallback(() => {
    setEditRecord(null);
    form.open();
  }, []);

  const handleEdit = useCallback((record: T) => {
    setEditRecord(record);
    form.open();
  }, []);

  const handleDelete = useCallback(
    (record: T) => {
      const displayName = String(record[nameKey] ?? '');
      confirm({
        title: t('confirm.deleteTitle'),
        content: t('confirm.deleteNamed', { label: nameLabel, name: displayName }),
        okText: t('action.ok'),
        cancelText: t('action.cancel'),
        onOk: async () => {
          try {
            await deleteMutation.mutateAsync(record.id);
            message.success(t('message.deleteSuccess'));
            refetch();
          } catch (err) {
            message.error(err instanceof Error ? err.message : t('message.deleteFailed'));
          }
        }
      });
    },
    [confirm, deleteMutation, nameKey, nameLabel, message, refetch, t]
  );

  const closeForm = useCallback(() => {
    form.close();
    setEditRecord(null);
    refetch();
  }, [refetch]);

  return {
    table,
    data,
    isLoading,
    refetch,
    formOpen: form.isOpen,
    editRecord,
    handleAdd,
    handleEdit,
    handleDelete,
    closeForm
  };
}
