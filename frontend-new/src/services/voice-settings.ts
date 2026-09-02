import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put, post } from '@/services/api-client';
import { queryKeys } from '@/services/query-keys';

/* ─── 类型 ──────────────────────────────────────────────────────── */

export interface VoiceConfig {
  provider: 'aliyun' | 'tencent';
  aliyun_access_key_id: string;
  aliyun_access_key_secret: string; // 脱敏值 "****" 或空
  aliyun_access_key_secret_set: boolean;
  aliyun_caller_number: string;
  aliyun_tts_code: string; // 语音模板 ID（TTS 路线）
  aliyun_tts_param: string;
  tencent_secret_id: string;
  tencent_secret_key: string; // 脱敏值 "****" 或空
  tencent_secret_key_set: boolean;
  tencent_app_id: string;
  tencent_template_id: string;
  play_times: number; // 1~3
  volume: number; // 0~100，腾讯云不支持
  speed: number; // -500~500，腾讯云不支持
  call_timeout: number;
  callback_token: string; // 脱敏值 "****" 或空
  callback_token_set: boolean;
  callback_verify_mode: 'ip_only' | 'signature_and_ip' | 'off';
  enabled: boolean;
}

export type VoiceConfigUpdate = Partial<Record<keyof VoiceConfig, unknown>>;

export interface VoiceChannelStatus {
  enabled: boolean;
  provider: string;
  ready: boolean;
  missing: string[];
  supports_ack: boolean;
  error?: string;
}

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
