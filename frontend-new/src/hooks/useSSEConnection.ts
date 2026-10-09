import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuthStore } from '@/stores/auth';
import { fetchSSETicket } from '@/services/sseTicket';

const FALLBACK_POLL_INTERVAL = 30_000;
const SSE_MAX_FAILURES = 3;
const SSE_DEGRADED_RETRY_INTERVAL = 5 * 60_000;

export type SSEStatus = 'idle' | 'connecting' | 'live' | 'degraded';

interface UseSSEConnectionOptions {
  url: string;
  enabled: boolean;
  onMessage: (data: string) => void;
  onFallbackPoll: () => void;
  label?: string;
}

export function useSSEConnection({
  url,
  enabled,
  onMessage,
  onFallbackPoll,
  label = 'SSE'
}: UseSSEConnectionOptions): { status: SSEStatus } {
  const token = useAuthStore((s) => s.token);

  const [status, setStatus] = useState<SSEStatus>('idle');
  const setStatusSafe = useCallback(
    (next: SSEStatus) => setStatus((prev) => (prev === next ? prev : next)),
    []
  );

  const lastTsRef = useRef<number>(0);
  const failCountRef = useRef<number>(0);

  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onFallbackPollRef = useRef(onFallbackPoll);
  onFallbackPollRef.current = onFallbackPoll;

  useEffect(() => {
    if (!enabled || !token) {
      setStatusSafe('idle');
      return;
    }
    setStatusSafe('connecting');

    let es: EventSource | null = null;
    let cancelled = false;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const startFallbackPolling = () => {
      if (fallbackTimer) return;
      console.warn(`[${label}] 连接不可用，已降级为定时轮询`);
      fallbackTimer = setInterval(() => onFallbackPollRef.current(), FALLBACK_POLL_INTERVAL);
    };

    const stopFallbackPolling = () => {
      if (fallbackTimer) {
        clearInterval(fallbackTimer);
        fallbackTimer = null;
      }
    };

    const closeEventSource = () => {
      if (!es) return;
      try {
        es.close();
      } catch {
      }
      es = null;
    };

    const degradeToPolling = () => {
      if (cancelled) return;
      closeEventSource();
      setStatusSafe('degraded');
      startFallbackPolling();
      if (retryTimer) return;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        failCountRef.current = 0;
        void connect();
      }, SSE_DEGRADED_RETRY_INTERVAL);
    };

    async function connect() {
      const ticket = await fetchSSETicket();
      if (cancelled) return;
      if (!ticket) {
        if (token) degradeToPolling();
        return;
      }
      const sseUrl = `${url}${url.includes('?') ? '&' : '?'}ticket=${encodeURIComponent(ticket)}`;

      try {
        es = new EventSource(sseUrl);

        es.onopen = () => {
          failCountRef.current = 0;
          stopFallbackPolling();
          setStatusSafe('live');
        };

        es.onmessage = (e: MessageEvent) => {
          try {
            const parsed = JSON.parse(e.data);
            if (parsed.op_type !== 'port_action_result') {
              if (parsed.ts && parsed.ts < lastTsRef.current) return;
              if (parsed.ts) lastTsRef.current = parsed.ts;
            }
            setStatusSafe('live');
            onMessageRef.current(e.data);
          } catch {
          }
        };

        es.onerror = () => {
          failCountRef.current += 1;
          if (failCountRef.current >= SSE_MAX_FAILURES) {
            degradeToPolling();
          } else {
            setStatusSafe('connecting');
          }
        };
      } catch {
        degradeToPolling();
      }
    }

    void connect();

    return () => {
      cancelled = true;
      closeEventSource();
      stopFallbackPolling();
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
    };
  }, [url, enabled, token, label, setStatusSafe]);

  return { status };
}
