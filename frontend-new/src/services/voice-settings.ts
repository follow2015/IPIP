import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put, post } from '@/services/api-client';
import { queryKeys } from '@/services/query-keys';
import type { components } from '@/types/api-generated';

/* ─── 类型（从 api-generated 桥接，Required 还原必选语义） ─────── */

export type VoiceConfig = Required<components['schemas']['VoiceConfig']>;
export type VoiceConfigUpdate = Partial<Record<keyof VoiceConfig, unknown>>;
export type VoiceChannelStatus = Required<components['schemas']['VoiceChannelStatus']>;

/* ─── API 函数 ──────────────────────────────────────────────────── */

async function fetchVoiceConfig(): Promise<VoiceConfig> {
  const res = await get<VoiceConfig>('/settings/voice');
  return res.data;
}

async function updateVoiceConfig(data: VoiceConfigUpdate): Promise<VoiceConfig> {
  const res = await put<VoiceConfig>('/settings/voice', data);
  return res.data;
}

async function testVoiceCall(
  data: VoiceConfigUpdate
): Promise<{ success: boolean; message: string }> {
  const res = await post<unknown>('/settings/voice/test', data);
  return { success: res.success, message: res.message };
}

async function fetchVoiceStatus(): Promise<VoiceChannelStatus> {
  const res = await get<VoiceChannelStatus>('/settings/voice/status');
  return res.data;
}

/* ─── Hooks ─────────────────────────────────────────────────────── */

export function useVoiceConfig() {
  return useQuery({
    queryKey: queryKeys.voiceSettings.config,
    queryFn: fetchVoiceConfig
  });
}

export function useVoiceChannelStatus() {
  return useQuery({
    queryKey: queryKeys.voiceSettings.status,
    queryFn: fetchVoiceStatus
  });
}

export function useUpdateVoiceConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updateVoiceConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.voiceSettings.all });
    }
  });
}

export function useTestVoiceCall() {
  return useMutation({
    mutationFn: testVoiceCall
  });
}
