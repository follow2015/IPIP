/**
 * 认证 Hook
 * - 封装 auth store 的登录/登出/权限检查方法
 */
import { useAuthStore } from '@/stores/auth';
import type { LoginRequest } from '@/types/api';
import type { User } from '@/types/models';

interface UseAuthReturn {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  permissions: string[];
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
}

export function useAuth(): UseAuthReturn {
  const { user, token, isAuthenticated, permissions, login, logout } =
    useAuthStore();
  return { user, token, isAuthenticated, permissions, login, logout };
}
