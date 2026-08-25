/**
 * 认证状态 store
 * 对齐后端 POST /auth/login 返回结构 { token, refresh_token, user, permissions }
 *
 * 重构改动：
 * 1. login()：去掉伪造的 created_at / updated_at（API 未返回），
 *    以空字符串占位并注释说明可通过 GET /auth/me 获取完整 profile
 * 2. localStorage 写入精简：api-client 只读取 'token'，
 *    无需额外写入 'user' / 'permissions'（zustand persist 已持久化完整 state）
 * 3. logout()：同步移除 'token'，其余由 zustand persist 的 partialize 控制清理
 * 4. 用 early return 替代嵌套 if，减少缩进层级
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { User } from '@/types/models';
import { login as apiLogin, logout as apiLogout } from '@/services/auth';
import type { LoginRequest, LoginResponse } from '@/types/api';


interface AuthState {
  user: User | null;
  token: string | null;
  permissions: string[];
  isAuthenticated: boolean;
  isVerifying: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
  clearAuth: () => void;
  checkAuth: () => boolean;
  setAuth: (user: User, token: string, permissions: string[]) => void;
  setVerifying: (verifying: boolean) => void;
}


function buildUserFromLogin(loginUser: LoginResponse['user']): User {
  return {
    id:           loginUser.id,
    username:     loginUser.username,
    email:        loginUser.email,
    name:         loginUser.name ?? '',
    real_name:    loginUser.name ?? '',     
    department:   null,
    contact_phone:null,
    roles:        loginUser.roles,
    is_active:    loginUser.is_active,
    status:       loginUser.status,
    
    created_at:   '',
    updated_at:   '',
  };
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user:            null,
      token:           null,
      permissions:     [],
      isAuthenticated: false,
      isVerifying:     false,

      login: async (credentials) => {
        const res = await apiLogin(credentials);
        if (!res.success || !res.data) {
          throw new Error(res.message || '登录失败');
        }
        const { token, user: loginUser, permissions } = res.data;
        const user = buildUserFromLogin(loginUser);
        set({ user, token, permissions: permissions ?? [], isAuthenticated: true });

        
        sessionStorage.setItem('token', token);
        
        if (res.data.refresh_token) {
          sessionStorage.setItem('refresh_token', res.data.refresh_token);
        }
      },

      logout: () => {
        
        const { token } = get();
        if (token) {
          apiLogout().catch(() => {});
        }
        set({ user: null, token: null, permissions: [], isAuthenticated: false, isVerifying: false });
        sessionStorage.removeItem('token');
        sessionStorage.removeItem('refresh_token');
      },

      
      clearAuth: () => {
        set({ user: null, token: null, permissions: [], isAuthenticated: false, isVerifying: false });
        sessionStorage.removeItem('token');
        sessionStorage.removeItem('refresh_token');
      },

      setVerifying: (verifying: boolean) => {
        set({ isVerifying: verifying });
      },

      checkAuth: () => {
        const { token, isAuthenticated } = get();
        return !!token && isAuthenticated;
      },

      setAuth: (user, token, permissions) => {
        set({ user, token, permissions, isAuthenticated: true });
        sessionStorage.setItem('token', token);
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        user:            state.user,
        token:           state.token,
        permissions:     state.permissions,
        isAuthenticated: state.isAuthenticated,
      }),
      
      onRehydrateStorage: () => (state) => {
        if (state && (!state.token || !state.isAuthenticated)) {
          state.user            = null;
          state.token           = null;
          state.permissions     = [];
          state.isAuthenticated = false;
          
          sessionStorage.removeItem('token');
          sessionStorage.removeItem('refresh_token');
        }
      },
    },
  ),
);
