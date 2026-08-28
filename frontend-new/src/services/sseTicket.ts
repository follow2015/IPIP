import { useAuthStore } from '@/stores/auth';

const SSE_TICKET_URL = '/api/sse/ticket';

let inflight: Promise<string | null> | null = null;

export async function fetchSSETicket(): Promise<string | null> {
  const token = useAuthStore.getState().token;
  if (!token) return null;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const res = await fetch(SSE_TICKET_URL, {
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
      inflight = null;
    }
  })();

  return inflight;
}
