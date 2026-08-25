/**
 * CRUD 工厂函数
 *
 * 核心思路：一个 CRUD 资源 = 一份声明式配置 → 自动生成全套 Service Hooks
 *
 * 使用示例：
 * ```ts
 * const roomHooks = createCrudHooks<Room, CreateRoomRequest, UpdateRoomRequest>({
 *   basePath: '/rooms',
 *   queryKey: queryKeys.rooms.all,
 * });
 * export const useRoomList   = roomHooks.useList;
 * export const useRoomDetail = roomHooks.useDetail;
 * export const useCreateRoom = roomHooks.useCreate;
 * export const useUpdateRoom = roomHooks.useUpdate;
 * export const useDeleteRoom = roomHooks.useDelete;
 * ```
 *
 * 扩展点：
 * - TParams:          useList 支持的完整查询参数类型（默认 PaginationParams）
 * - createPath:       创建端点与 basePath 不同时指定（如 User 走 /auth/register）
 * - toUpdatePayload:  更新请求体转换（如 {id, data} → data）
 * - optionsConfig:    下拉选项的自定义路径和字段映射
 */
import {
  useQuery,
  useSuspenseQuery,
  useMutation,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
  type UseSuspenseQueryResult,
} from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { toSelectOptions } from './service-utils';
import type { ApiResponse, PaginatedData, PaginationParams } from '@/types/api';


export interface SelectOption {
  label: string;
  value: string | number;
}


export interface CrudConfig<T, TCreate extends object, TUpdate extends { id: number }> {
  
  basePath: string;
  
  queryKey: readonly unknown[];
  
  createPath?: string;
  
  getId?: (data: TUpdate) => number;
  
  toUpdatePayload?: (data: TUpdate) => object;
  
  optionsConfig?: {
    
    path?: string;
    
    paginated?: boolean;
    
    labelKey?: keyof T;
    
    valueKey?: keyof T;
  };
}


export interface CrudHooks<
  T,
  TCreate extends object,
  TUpdate extends { id: number },
  TParams extends PaginationParams = PaginationParams,
> {
  
  useList: (params?: TParams) => UseQueryResult<PaginatedData<T>, Error>;
  
  useDetail: (id: number, options?: { enabled?: boolean }) => UseQueryResult<T, Error>;
  
  useSuspenseDetail: (id: number) => UseSuspenseQueryResult<T, Error>;
  
  useCreate: () => UseMutationResult<ApiResponse<T>, Error, TCreate, unknown>;
  
  useUpdate: () => UseMutationResult<ApiResponse<T>, Error, TUpdate, unknown>;
  
  useDelete: () => UseMutationResult<ApiResponse<void>, Error, number, unknown>;
  
  useOptions: () => UseQueryResult<SelectOption[], Error>;
}


function defaultGetId<T extends { id: number }>(data: T): number {
  return data.id;
}


function defaultToUpdatePayload<T extends { id: number }>(data: T): object {
  const { id, ...rest } = data;
  return rest;
}


export function createCrudHooks<
  T extends object,
  TCreate extends object,
  TUpdate extends { id: number },
  TParams extends PaginationParams = PaginationParams,
>(config: CrudConfig<T, TCreate, TUpdate>): CrudHooks<T, TCreate, TUpdate, TParams> {
  const {
    basePath,
    queryKey,
    createPath = basePath,
    getId = defaultGetId as (data: TUpdate) => number,
    toUpdatePayload = defaultToUpdatePayload as (data: TUpdate) => object,
    optionsConfig,
  } = config;

  
  function useList(params?: TParams) {
    return useQuery({
      queryKey: [...queryKey, 'list', params],
      queryFn: async () => {
        const res = await get<PaginatedData<T>>(basePath, params as Record<string, unknown>);
        return res.data;
      },
    });
  }

  
  function useDetail(id: number, options?: { enabled?: boolean }) {
    return useQuery({
      queryKey: [...queryKey, id],
      queryFn: async () => {
        const res = await get<T>(`${basePath}/${id}`);
        return res.data;
      },
      enabled: options?.enabled ?? id > 0,
    });
  }

  
  function useSuspenseDetail(id: number) {
    return useSuspenseQuery({
      queryKey: [...queryKey, id],
      queryFn: async () => {
        const res = await get<T>(`${basePath}/${id}`);
        return res.data;
      },
    });
  }

  
  function useCreate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (data: TCreate) => post<T, TCreate>(createPath, data),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey });
      },
    });
  }

  
  function useUpdate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (data: TUpdate) => {
        const id = getId(data);
        const payload = toUpdatePayload(data);
        return put<T>(`${basePath}/${id}`, payload);
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey });
      },
    });
  }

  
  function useDelete() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (id: number) => del<void>(`${basePath}/${id}`),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey });
      },
    });
  }

  
  function useOptions() {
    const optPath = optionsConfig?.path ?? `${basePath}/all`;
    const paginated = optionsConfig?.paginated ?? false;
    const labelKey = (optionsConfig?.labelKey ?? 'name') as keyof T;
    const valueKey = (optionsConfig?.valueKey ?? 'id') as keyof T;

    return useQuery({
      queryKey: [...queryKey, 'options'],
      queryFn: async (): Promise<SelectOption[]> => {
        if (paginated) {
          const res = await get<PaginatedData<T>>(basePath, { per_page: 999 });
          return toSelectOptions(res.data?.items ?? [], labelKey, valueKey) as SelectOption[];
        }
        const res = await get<T[]>(optPath);
        return toSelectOptions(res.data ?? [], labelKey, valueKey) as SelectOption[];
      },
    });
  }

  return { useList, useDetail, useSuspenseDetail, useCreate, useUpdate, useDelete, useOptions };
}
