/**
 * 用户服务
 * - 列表/创建/更新通过 createCrudHooks 生成（创建走 /users/register）
 * - 删除走 /users/batch-delete（后端无单删端点）
 * - 状态切换、密码操作、当前用户、权限查询仍手写
 * 对齐后端 /api/users/* 和 /api/auth/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put } from './api-client';
import { createCrudHooks } from './crud-factory';
import { queryKeys } from './query-keys';
import type { User, Permission } from '@/types/models';
import type { PaginatedData, PaginationParams } from '@/types/api';


export interface CreateUserRequest {
  username: string;
  password: string;
  email: string;
  name?: string;
  department?: string;
  contact_phone?: string;
}


export interface UpdateUserRequest {
  id: number;
  data: Partial<Omit<CreateUserRequest, 'password'>> & { status?: number };
}


export interface UserQueryParams extends PaginationParams {
  search?: string;
}


const userHooks = createCrudHooks<User, CreateUserRequest, UpdateUserRequest, UserQueryParams>({
  basePath: '/users',
  queryKey: queryKeys.users.all,
  createPath: '/users/register',
  getId: (data) => data.id,
  toUpdatePayload: (data) => data.data,
});

export const useUserList   = userHooks.useList;
export const useUserDetail = userHooks.useDetail;
export const useCreateUser = userHooks.useCreate;
export const useUpdateUser = userHooks.useUpdate;


export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => post<null>('/users/batch-delete', { ids: [id] }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}


export function useUserOptions() {
  return useQuery({
    queryKey: [...queryKeys.users.all, 'options'],
    queryFn: async () => {
      const res = await get<PaginatedData<User>>('/users', { per_page: 999, page: 1 });
      const users = res.data?.items ?? [];
      return users
        .filter((u) => u.is_active)
        .map((u) => ({
          label: `${u.name || u.username}${u.department ? ` (${u.department})` : ''}`,
          value: u.id,
        }));
    },
  });
}


export function useCurrentUser() {
  return useQuery({
    queryKey: queryKeys.users.me,
    queryFn: async () => {
      const res = await get<User>('/users/me');
      return res.data;
    },
  });
}


export interface LoginLog {
  id: number;
  user_id: number;
  username: string | null;
  name: string | null;
  login_time: string;
  login_type: string;
  login_ip: string | null;
  user_agent: string | null;
}


export function useLoginLogs(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.users.loginLogs(params),
    queryFn: async () => {
      const res = await get<PaginatedData<LoginLog>>('/users/me/login-logs', params);
      return res.data;
    },
  });
}


export interface LoginLogQueryParams extends PaginationParams {
  user_id?: number;
  start_time?: string;
  end_time?: string;
}


export function useAllLoginLogs(params?: LoginLogQueryParams) {
  return useQuery({
    queryKey: [...queryKeys.users.all, 'all-login-logs', params],
    queryFn: async () => {
      const res = await get<PaginatedData<LoginLog>>('/users/login-logs', params);
      return res.data;
    },
  });
}


export function useUserLoginLogs(userId: number, params?: PaginationParams) {
  return useQuery({
    queryKey: [...queryKeys.users.all, userId, 'login-logs', params],
    queryFn: async () => {
      const res = await get<PaginatedData<LoginLog>>(`/users/${userId}/login-logs`, params);
      return res.data;
    },
    enabled: userId > 0,
  });
}


export function useUserPermissions(userId: number) {
  return useQuery({
    queryKey: queryKeys.users.permissions(userId),
    queryFn: async () => {
      const res = await get<Permission[]>(`/users/${userId}/permissions`);
      return res.data;
    },
    enabled: userId > 0,
  });
}


export function useToggleUserStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: number }) =>
      put<User>(`/users/${id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}


export function useChangePassword() {
  return useMutation({
    mutationFn: ({ old_password, new_password }: { old_password: string; new_password: string }) =>
      post<null>('/users/change-password', { old_password, new_password }),
  });
}


export interface UpdateMyProfileRequest {
  username?: string;
  name?: string;
  email?: string;
  contact_phone?: string;
}


export function useUpdateMyProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateMyProfileRequest) => put<User>('/users/me/profile', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.me });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}


export function useResetPassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => post<{ reset: boolean; new_password: string }>(`/users/${id}/reset-password`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}
