import { useAuthStore } from '@/stores/auth';

const SSE_TICKET_URL = '/api/sse/ticket';

const inflight = new Map<string, Promise<string | null>>();

export async function fetchSSETicket(deviceId?: number | string): Promise<string | null> {
  const token = useAuthStore.getState().token;
  if (!token) return null;

  const key = deviceId === undefined ? '__global__' : String(deviceId);
  const pending = inflight.get(key);
  if (pending) return pending;

  const url =
    deviceId === undefined
      ? SSE_TICKET_URL
      : `${SSE_TICKET_URL}?device_id=${encodeURIComponent(String(deviceId))}`;

  const task = (async () => {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (!res.ok) return null;
      const json = (await res.json()) as { data?: { ticket?: string } };
      return json?.data?.ticket ?? null;
    } catch {
      return null;
    } finally {
      inflight.delete(key);
    }
  })();

  inflight.set(key, task);
  return task;
}
