/**
 * useSSEConnection — SSE 连接管理公共 Hook（CR-24）
 *
 * 封装 EventSource 创建/销毁、token 认证、回退轮询降级、失败计数等通用逻辑，
 * 供 useGlobalEvents 复用，消除重复代码。
 *
 * ⚠️ 职责边界说明：
 * 本 Hook 仅负责全局 SSE 事件流（/realtime/sse/global）的连接管理，
 * 即非设备维度的全局事件（如 room_scan_complete、scan_complete 等）。
 * 设备维度的 SSE 事件订阅由 DeviceEventBus（纯 TS 类）统一管理，
 * 两者职责不重叠：DeviceEventBus 负责设备级事件分发与缓存失效，
 * useSSEConnection 负责全局事件流的连接生命周期与降级策略。
 *
 * SSE 服务已从 Flask 迁移至独立 ASGI 推送网关（realtime_gateway/），
 * 通过反向代理 /realtime/ 路径访问，不直接暴露网关端口。
 *
 * 使用方式：
 * ```ts
 * useSSEConnection({
 *   url: '/api/switch/events',
 *   enabled: true,
 *   onMessage: (data) => { ... },
 *   onFallbackPoll: () => { ... },
 * });
 * ```
 */
import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/stores/auth';


const FALLBACK_POLL_INTERVAL = 30_000;

const SSE_MAX_FAILURES = 3;

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
  label = 'SSE',
}: UseSSEConnectionOptions) {
  
  const token = useAuthStore(s => s.token);

  
  const lastTsRef = useRef<number>(0);
  
  const failCountRef = useRef<number>(0);

  
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onFallbackPollRef = useRef(onFallbackPoll);
  onFallbackPollRef.current = onFallbackPoll;

  useEffect(() => {
    if (!enabled || !token) return;

    const sseUrl = `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
    let es: EventSource | null = null;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;

    
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

    try {
      es = new EventSource(sseUrl);

      es.onopen = () => {
        failCountRef.current = 0;
        stopFallbackPolling();
      };

      es.onmessage = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          
          if (parsed.op_type !== 'port_action_result') {
            
            if (parsed.ts && parsed.ts < lastTsRef.current) return;
            if (parsed.ts) lastTsRef.current = parsed.ts;
          }
          onMessageRef.current(e.data);
        } catch {
          
        }
      };

      es.onerror = () => {
        failCountRef.current += 1;
        if (failCountRef.current >= SSE_MAX_FAILURES) {
          startFallbackPolling();
        }
      };
    } catch {
      startFallbackPolling();
    }

    return () => {
      es?.close();
      stopFallbackPolling();
    };
  }, [url, enabled, token, label]);
}
