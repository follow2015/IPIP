/**
 * 设备配置管理服务
 * - 获取最新配置快照
 * - 配置变更历史
 * - 触发配置备份
 * - 提交配置变更请求
 * 对齐后端 /api/devices/:id/config/* 端点
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post } from './api-client';
import { queryKeys } from './query-keys';
import type { DeviceConfigBackup, DeviceConfigChange } from '@/types/models';
import type { ApiResponse } from '@/types/api';

export function useDeviceConfig(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.deviceConfig.detail(deviceId),
    queryFn: async () => {
      const res = await get<DeviceConfigBackup>(`/devices/${deviceId}/config`);
      return res.data;
    },
    enabled: deviceId > 0,
  });
}

export function useDeviceConfigHistory(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.deviceConfig.history(deviceId),
    queryFn: async () => {
      const res = await get<DeviceConfigBackup[]>(`/devices/${deviceId}/config/history`);
      return res.data;
    },
    enabled: deviceId > 0,
  });
}

export function useBackupDeviceConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: number) =>
      post<DeviceConfigBackup>(`/devices/${deviceId}/config/backup`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deviceConfig.all });
    },
  });
}

export function useSubmitConfigChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, data }: { deviceId: number; data: Partial<DeviceConfigChange> }) =>
      post<ApiResponse<DeviceConfigChange>>(`/devices/${deviceId}/config/change`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deviceConfig.all });
    },
  });
}

export function useDeviceConfigChanges(deviceId: number) {
  return useQuery({
    queryKey: [...queryKeys.deviceConfig.history(deviceId), 'changes'],
    queryFn: async () => {
      const res = await get<DeviceConfigChange[]>(`/devices/${deviceId}/config/changes`);
      return res.data;
    },
    enabled: deviceId > 0,
  });
}

export function useApproveConfigChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, changeId, action }: { deviceId: number; changeId: number; action: 'approve' | 'reject' }) =>
      post<ApiResponse<DeviceConfigChange>>(`/devices/${deviceId}/config/changes/${changeId}/${action}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deviceConfig.all });
    },
  });
}
