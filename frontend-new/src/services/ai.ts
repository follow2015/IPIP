import { post, get, put, del } from '@/services/api-client';
import { fetchSSETicket } from '@/services/sseTicket';
import type { components } from '@/types/api-generated';

const AI_TIMEOUT_MS = 60_000;

export async function runSkill<T = unknown>(
  name: string,
  args: Record<string, unknown> = {}
): Promise<T> {
  const res = await post<{ result: T }>(`/ai/skills/${encodeURIComponent(name)}/run`, args, {
    timeout: AI_TIMEOUT_MS
  });
  return res.data.result;
}

export async function ask(question: string, signal?: AbortSignal): Promise<string> {
  const res = await post<{ answer: string }>(
    '/ai/ask',
    { question },
    { timeout: AI_TIMEOUT_MS, signal }
  );
  return res.data.answer;
}

export type SkillSummary = Required<components['schemas']['AISkillSummary']>;

export type SkillDetail = Required<components['schemas']['AISkillDetail']>;

export async function listSkills(): Promise<SkillSummary[]> {
  const res = await get<{ skills: SkillSummary[] }>('/ai/skills');
  return res.data.skills;
}

export async function getSkill(name: string): Promise<SkillDetail> {
  const res = await get<{ skill: SkillDetail }>(`/ai/skills/${encodeURIComponent(name)}`);
  return res.data.skill;
}

export async function toggleSkill(name: string, enabled: boolean): Promise<void> {
  await put<{ ok: boolean }>(`/ai/skills/${encodeURIComponent(name)}`, { enabled });
}

export async function reloadSkills(): Promise<number> {
  const res = await post<{ count: number }>('/ai/skills/reload', {});
  return res.data.count;
}

export interface SkillWritePayload {
  name: string;
  title?: string;
  description: string;
  category?: string;
  version?: number;
  max_llm_steps?: number;
  params: Array<{
    name: string;
    type: string;
    required?: boolean;
    description?: string;
  }>;
  triggers: string[];
  steps: Array<{
    id: string;
    type?: 'capability' | 'llm' | 'route';
    call: string;
    args?: Record<string, unknown>;
    output?: string;
    when?: string;
    max_tokens?: number;
    branches?: Record<string, string>;
  }>;
  return?: unknown;
}

export async function createSkill(payload: SkillWritePayload): Promise<void> {
  await post<{ ok: boolean }>('/ai/skills', payload);
}

export async function updateSkillContent(name: string, payload: SkillWritePayload): Promise<void> {
  await put<{ ok: boolean }>(`/ai/skills/${encodeURIComponent(name)}/content`, payload);
}

export async function deleteSkill(name: string): Promise<void> {
  await del<{ ok: boolean }>(`/ai/skills/${encodeURIComponent(name)}`);
}

export type AIConfig = Required<components['schemas']['AIConfigResponse']>;

export type AIConfigUpdate = components['schemas']['AIConfigUpdateRequest'];

export async function getAIConfig(): Promise<AIConfig> {
  const res = await get<AIConfig>('/ai/config');
  return res.data;
}

export async function updateAIConfig(
  updates: AIConfigUpdate
): Promise<AIConfig & { changed: string[] }> {
  const res = await put<AIConfig & { changed: string[] }>('/ai/config', updates);
  return res.data;
}

export type CircuitStatus = Required<components['schemas']['AICircuitStatusItem']>;

export async function getCircuitStatus(): Promise<CircuitStatus[]> {
  const res = await get<{ providers: CircuitStatus[] }>('/ai/circuit');
  return res.data.providers;
}

export async function resetCircuit(provider: string): Promise<void> {
  await post<{ ok: boolean }>('/ai/circuit/reset', { provider });
}

export type AIMetrics = Required<components['schemas']['AIMetricsResponse']> & {
  [key: string]: unknown;
};

export async function getAIMetrics(): Promise<AIMetrics> {
  const res = await get<AIMetrics>('/ai/metrics');
  return res.data;
}


export type AIHealth = Required<components['schemas']['AIHealthResponse']>;

export async function getAIHealth(): Promise<AIHealth> {
  const res = await get<AIHealth>('/ai/health');
  return res.data;
}

export type AgenticSkillSummary = Required<components['schemas']['AIAgenticSkillSummary']>;

export async function listAgenticSkills(): Promise<AgenticSkillSummary[]> {
  const res = await get<{ skills: AgenticSkillSummary[] }>('/ai/agentic/skills');
  return res.data.skills;
}

export type AgenticRunResponse = Required<components['schemas']['AIAsyncTaskResponse']>;

export async function runAgenticSkill(
  name: string,
  question: string,
  idempotencyKey?: string
): Promise<AgenticRunResponse> {
  const body: Record<string, unknown> = { question };
  if (idempotencyKey) {
    body.idempotency_key = idempotencyKey;
  }
  const res = await post<AgenticRunResponse>(
    `/ai/agentic/skills/${encodeURIComponent(name)}/run`,
    body,
    { timeout: AI_TIMEOUT_MS }
  );
  return res.data;
}

export type RagIngestRequest = Required<components['schemas']['AIRagIngestRequest']>;
export type RagIngestResponse = Required<components['schemas']['AIRagIngestResponse']>;

export async function ragIngest(req: RagIngestRequest): Promise<RagIngestResponse> {
  const res = await post<RagIngestResponse>('/ai/rag/ingest', req, { timeout: AI_TIMEOUT_MS });
  return res.data;
}

export interface RagIngestProgressEvent {
  type: 'progress' | 'done' | 'error';
  status?: string;
  progress?: number;
  total?: number;
  message?: string;
  result?: unknown;
}


export interface TaskProgressEvent {
  type: 'progress' | 'done' | 'error';
  status?: string;
  progress?: number;
  total?: number;
  result?: unknown;
  session_id?: number;
  user_id?: number;
  message?: string;
}

function _subscribeSSEProgress<TEvent extends { type: string }>(
  urlBase: string,
  onEvent: (event: TEvent) => void,
  onError?: (err: Event) => void
): { cancel: () => void } {
  let es: EventSource | null = null;
  let cancelled = false;
  let completed = false;

  (async () => {
    const ticket = await fetchSSETicket();
    if (cancelled) return;
    if (!ticket) {
      if (onError) onError(new Event('error'));
      return;
    }
    const url = `${urlBase}?ticket=${encodeURIComponent(ticket)}`;
    es = new EventSource(url);

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as TEvent;
        onEvent(data);
        if (data.type === 'done' || data.type === 'error') {
          completed = true;
          es?.close();
        }
      } catch {
      }
    };

    es.onerror = (err) => {
      if (completed || cancelled) return;
      if (onError) onError(err);
      es?.close();
    };
  })();

  return {
    cancel: () => {
      cancelled = true;
      es?.close();
    }
  };
}

export function subscribeRagIngestProgress(
  taskId: string,
  onEvent: (event: RagIngestProgressEvent) => void,
  onError?: (err: Event) => void
): { cancel: () => void } {
  return _subscribeSSEProgress(
    `/realtime/sse/ai-task/${encodeURIComponent(taskId)}`,
    onEvent,
    onError
  );
}

export function subscribeTaskProgress(
  taskId: string,
  onEvent: (event: TaskProgressEvent) => void,
  onError?: (err: Event) => void
): { cancel: () => void } {
  return _subscribeSSEProgress(
    `/api/ai/task/progress/${encodeURIComponent(taskId)}`,
    onEvent,
    onError
  );
}


export type RagStatus = Required<components['schemas']['AIRagStatusResponse']>;

export async function getRagStatus(): Promise<RagStatus> {
  const res = await get<RagStatus>('/ai/rag/status');
  return res.data;
}

export type RagDoc = Required<components['schemas']['AIRagDoc']>;

export async function listRagDocs(limit = 100, offset = 0): Promise<{ docs: RagDoc[] }> {
  const res = await get<{ docs: RagDoc[] }>(`/ai/rag/docs?limit=${limit}&offset=${offset}`);
  return res.data;
}

export async function deleteRagDoc(docId: string): Promise<void> {
  await del(`/ai/rag/docs/${encodeURIComponent(docId)}`);
}

export async function resetRagStore(): Promise<void> {
  await post<{ ok: boolean }>('/ai/rag/reset', { confirm: true });
}

export async function ragQa(question: string): Promise<string> {
  const res = await post<{ answer: string }>(
    '/ai/rag/qa',
    { question },
    { timeout: AI_TIMEOUT_MS }
  );
  return res.data.answer;
}
