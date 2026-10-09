/**
 * 认证初始化 Hook
 *
 * 应用启动时验证 rehydrate 的 token 是否仍有效。
 * CR-27: 先做本地 JWT exp 检查（零网络开销），过期则立即清理；
 * 未过期再调 /auth/profile 确认服务端也认可。
 */
import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/stores/auth';
import { verifyToken } from '@/services/auth';

type JwtExpiry = 'valid' | 'expired' | 'unparsable';

function checkJwtExpiry(token: string): JwtExpiry {
  try {
    const b64 = token.split('.')[1];
    if (!b64) return 'unparsable';
    const bin = atob(b64.replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const payload: unknown = JSON.parse(new TextDecoder().decode(bytes));
    const exp = (payload as { exp?: unknown } | null)?.exp;
    if (typeof exp !== 'number') return 'unparsable';
    return exp * 1000 < Date.now() ? 'expired' : 'valid';
  } catch {
    return 'unparsable';
  }
}

export function useAuthInit() {
  const initRef = useRef(false);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    const { token, isAuthenticated } = useAuthStore.getState();

    if (!token || !isAuthenticated) return;

    const expiry = checkJwtExpiry(token);
    if (expiry === 'expired') {
      useAuthStore.getState().clearAuth();
      return;
    }

    useAuthStore.getState().setVerifying(true);

    verifyToken()
      .then((res) => {
        if (!res.success || !res.data) {
          useAuthStore.getState().clearAuth();
        }
      })
      .catch(() => {
        useAuthStore.getState().clearAuth();
      })
      .finally(() => {
        useAuthStore.getState().setVerifying(false);
      });
  }, []);
}
