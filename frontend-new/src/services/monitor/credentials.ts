
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, del, patch, put } from '../api-client';
import { queryKeys } from '../query-keys';

import type { components } from '@/types/api-generated';

export type MonitorCredentialListItem = components['schemas']['MonitorCredentialListItem'];

export interface LinkedDevice {
  device_id: number;
  device_name: string;
  device_type: string;
  management_ip: string | null;
}

export function useMonitorCredentials() {
  return useQuery({
    queryKey: queryKeys.monitor.credentials(),
    queryFn: async () => {
      const res = await get<MonitorCredentialListItem[]>('/monitor/credentials');
      return res.data ?? [];
    }
  });
}

export function useLinkedDevices(credentialId: number | null) {
  return useQuery({
    queryKey: queryKeys.monitor.linkedDevices(credentialId ?? 0),
    queryFn: async () => {
      const res = await get<LinkedDevice[]>(`/monitor/credentials/${credentialId}/devices`);
      return res.data ?? [];
    },
    enabled: credentialId != null && credentialId > 0
  });
}

export function usePatchCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { credentialId: number; enabled?: boolean; name?: string }) => {
      const res = await patch(`/monitor/credentials/${input.credentialId}`, {
        enabled: input.enabled,
        name: input.name
      });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useDeleteCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (credentialId: number) => {
      const res = await del(`/monitor/credentials/${credentialId}`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useBatchDeleteCredentials() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await post('/monitor/credentials/batch-delete', { ids });
      return res.data as { deleted: number; failed: { id: number; reason: string }[] };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useCreateAndLinkCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      protocol: string;
      payload: Record<string, unknown>;
      name?: string;
      device_ids: number[];
    }) => {
      const res = await post('/monitor/credentials', input);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useLinkExistingCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { credentialId: number; device_ids: number[] }) => {
      const res = await post(`/monitor/credentials/${input.credentialId}/link`, {
        device_ids: input.device_ids
      });
      return res.data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      vars.device_ids.forEach((id) =>
        qc.invalidateQueries({ queryKey: queryKeys.monitor.status(id) })
      );
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUnlinkCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { deviceId: number; protocol: string }) => {
      const res = await del(`/monitor/devices/${input.deviceId}/credentials/${input.protocol}`);
      return res.data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(vars.deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUpdateSharedCredentialPayload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      credentialId: number;
      payload: Record<string, unknown>;
      name?: string;
    }) => {
      const res = await put<components['schemas']['MonitorCredentialPayloadUpdateResponse']>(
        `/monitor/credentials/${input.credentialId}/payload`,
        {
          payload: input.payload,
          name: input.name
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}

export function useUpdateCredentialPayload(deviceId: number, credentialId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { payload: Record<string, unknown>; name?: string }) => {
      const res = await put<components['schemas']['MonitorCredentialPayloadUpdateResponse']>(
        `/monitor/devices/${deviceId}/credentials/${credentialId}/payload`,
        {
          payload: input.payload,
          name: input.name
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.monitor.status(deviceId) });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.credentials() });
      qc.invalidateQueries({ queryKey: queryKeys.monitor.metricDashboardAll });
    }
  });
}
