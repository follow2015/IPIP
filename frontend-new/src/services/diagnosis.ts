import { post, get } from '@/services/api-client';
import type { components } from '@/types/api-generated';

const AI_TIMEOUT_MS = 90_000; // 诊断多轮可能较慢



export interface ProposedCommand {
  command_key: string;
  type: 'diagnostic' | 'remedial';
  risk_level?: 'none' | 'low' | 'medium' | 'high';
  params?: Record<string, unknown>;
  rollback_command_key?: string;
}

export type RemedialPreview = Required<components['schemas']['AIRemedialPreviewResponse']>;

export interface DiagnosisResult {
  diagnosis: string;
  confidence: number;
  evidence: string[];
  proposed_commands: ProposedCommand[];
  incomplete?: boolean;
  anomalous_metrics?: string[];
  pre_snapshot?: Record<string, number>;
}

export type RemedialAsyncResponse = Required<components['schemas']['AIAsyncTaskResponse']>;

export type VerificationResult = Required<components['schemas']['AIVerificationResponse']> & {
  status: 'recovered' | 'partial' | 'not_recovered';
};

export type RollbackFailure = Required<components['schemas']['AIDiagnosisSession']>;


export interface DiagnoseResponse {
  result: DiagnosisResult;
  sessionId?: number;
}

export function parseDiagnosisAnswer(answer: string): DiagnosisResult {
  try {
    return JSON.parse(answer) as DiagnosisResult;
  } catch {
    return {
      diagnosis: answer,
      confidence: 0,
      evidence: [],
      proposed_commands: []
    };
  }
}

export async function diagnose(question: string, signal?: AbortSignal): Promise<DiagnoseResponse> {
  const res = await post<{ answer: string; session_id?: number }>(
    '/ai/ask',
    { question },
    { timeout: AI_TIMEOUT_MS, signal }
  );
  return {
    result: parseDiagnosisAnswer(res.data.answer),
    sessionId: res.data.session_id
  };
}

export async function previewRemedial(
  deviceId: number,
  commandKey: string,
  params: Record<string, unknown> = {}
): Promise<RemedialPreview> {
  const res = await post<RemedialPreview>('/ai/diagnosis/remedial/preview', {
    device_id: deviceId,
    command_key: commandKey,
    params
  });
  return res.data;
}

export async function executeRemedial(
  deviceId: number,
  commandKey: string,
  params: Record<string, unknown> = {},
  sessionId?: number,
  idempotencyKey?: string
): Promise<RemedialAsyncResponse> {
  if (!idempotencyKey) {
    throw new Error('idempotencyKey 必填（防命令重复下发）');
  }
  const res = await post<RemedialAsyncResponse>(
    '/ai/diagnosis/remedial/execute',
    {
      device_id: deviceId,
      command_key: commandKey,
      params,
      session_id: sessionId,
      confirmed: true,
      idempotency_key: idempotencyKey
    },
    { timeout: AI_TIMEOUT_MS }
  );
  return res.data;
}

export async function rollbackRemedial(
  deviceId: number,
  rollbackCommandKey: string,
  params: Record<string, unknown> = {},
  sessionId?: number
): Promise<{ success: boolean; output: string }> {
  const res = await post<{ success: boolean; output: string }>(
    '/ai/diagnosis/remedial/rollback',
    {
      device_id: deviceId,
      rollback_command_key: rollbackCommandKey,
      params,
      session_id: sessionId
    },
    { timeout: AI_TIMEOUT_MS }
  );
  return res.data;
}

export async function verifyRemediation(
  deviceId: number,
  preSnapshot: Record<string, number>,
  anomalousMetrics: string[]
): Promise<VerificationResult> {
  const res = await post<VerificationResult>(
    '/ai/diagnosis/verify',
    {
      device_id: deviceId,
      pre_snapshot: preSnapshot,
      anomalous_metrics: anomalousMetrics
    },
    { timeout: AI_TIMEOUT_MS }
  );
  return res.data;
}

export async function caseToRag(
  symptom: string,
  evidence: string[],
  rootCause: string,
  remedialCommands: ProposedCommand[],
  verifiedStatus: string
): Promise<boolean> {
  const res = await post<{ success: boolean }>('/ai/diagnosis/case-to-rag', {
    symptom,
    evidence,
    root_cause: rootCause,
    remedial_commands: remedialCommands,
    verified_status: verifiedStatus
  });
  return res.data.success;
}

export async function getRollbackFailures(): Promise<
  Required<components['schemas']['AIRollbackFailuresResponse']>
> {
  const res = await get<Required<components['schemas']['AIRollbackFailuresResponse']>>(
    '/ai/diagnosis/rollback-failures'
  );
  return res.data;
}

export async function getDiagnosisSessions(
  deviceId?: number,
  limit = 20
): Promise<RollbackFailure[]> {
  const params: Record<string, number> = { limit };
  if (deviceId) params.device_id = deviceId;
  const res = await get<Required<components['schemas']['AIDiagnosisSessionsResponse']>>(
    '/ai/diagnosis/sessions',
    params
  );
  return res.data.sessions;
}
