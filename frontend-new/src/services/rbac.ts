/**
 * RBAC 权限服务
 * - 角色 CRUD 通过 createCrudHooks 生成
 * - 权限列表、分类、角色权限、用户角色、设置权限/角色仍手写
 * 对齐后端 /api/rbac/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import { toSelectOptions } from './service-utils';
import type { Role, RoleDetail, Permission } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';

export interface CreateRoleRequest {
  name: string;
  display_name: string;
  description?: string;
}

export interface UpdateRoleRequest {
  id: number;
  data: Partial<CreateRoleRequest>;
}


const roleHooks = createCrudHooks<Role & { permission_count?: number; user_count?: number }, CreateRoleRequest, UpdateRoleRequest>({
  basePath: '/rbac/roles',
  queryKey: queryKeys.rbac.all,
  getId: (data) => data.id,
  toUpdatePayload: (data) => data.data,
});

export const useRoleList   = roleHooks.useList;
export const useRoleDetail = roleHooks.useDetail;
export const useCreateRole = roleHooks.useCreate;
export const useUpdateRole = roleHooks.useUpdate;
export const useDeleteRole = roleHooks.useDelete;


export function usePermissionList(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.rbac.permissions(params),
    queryFn: async () => {
      const res = await get<PaginatedData<Permission>>('/rbac/permissions', { per_page: 999, ...params });
      return res.data;
    },
  });
}

export function usePermissionCategories() {
  return useQuery({
    queryKey: queryKeys.rbac.categories,
    queryFn: async () => {
      const res = await get<string[]>('/rbac/permissions/categories');
      return res.data;
    },
  });
}

export function useRolePermissions(roleId: number) {
  return useQuery({
    queryKey: queryKeys.rbac.rolePermissions(roleId),
    queryFn: async () => {
      const res = await get<Permission[]>(`/rbac/roles/${roleId}/permissions`);
      return res.data;
    },
    enabled: roleId > 0,
  });
}

export function useUserRoles(userId: number) {
  return useQuery({
    queryKey: queryKeys.rbac.userRoles(userId),
    queryFn: async () => {
      const res = await get<Role[]>(`/rbac/users/${userId}/roles`);
      return res.data;
    },
    enabled: userId > 0,
  });
}

export function useSetRolePermissions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, permissions }: { roleId: number; permissions: string[] }) =>
      put<null>(`/rbac/roles/${roleId}/permissions`, { permissions }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rbac.all });
    },
  });
}

export function useSetUserRoles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, roles }: { userId: number; roles: string[] }) =>
      put<null>(`/rbac/users/${userId}/roles`, { roles }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.rbac.all });
    },
  });
}

export function useRoleOptions() {
  return useQuery({
    queryKey: queryKeys.rbac.options,
    queryFn: async () => {
      const res = await get<PaginatedData<Role>>('/rbac/roles', { per_page: 999 });
      return toSelectOptions(res.data?.items ?? [], 'display_name', 'id') as { label: string; value: string | number }[];
    },
  });
}
