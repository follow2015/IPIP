import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useAuthStore } from './auth';
import type { User } from '@/types/models';
import type { ApiResponse, LoginResponse } from '@/types/api';

const { loginMock, logoutMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  logoutMock: vi.fn()
}));

vi.mock('@/services/auth', () => ({
  login: (...args: unknown[]) => loginMock(...args),
  logout: (...args: unknown[]) => logoutMock(...args)
}));

type LoginResult = ApiResponse<LoginResponse>;

function makeUser(roles: string[]): User {
  return {
    id: 1,
    username: 'u',
    email: '',
    name: '',
    real_name: '',
    department: null,
    contact_phone: null,
    roles,
    is_active: true,
    status: 'active',
    created_at: '',
    updated_at: ''
  } as unknown as User;
}

beforeEach(() => {
  sessionStorage.clear();
  loginMock.mockReset();
  logoutMock.mockReset();
  logoutMock.mockResolvedValue(undefined);
  useAuthStore.setState({
    user: null,
    token: null,
    permissions: [],
    isAuthenticated: false,
    isVerifying: false
  });
});

describe('useAuthStore', () => {
  it('login 成功写入 state + sessionStorage', async () => {
    loginMock.mockResolvedValue({
      success: true,
      message: '',
      data: {
        token: 't1',
        refresh_token: 'r1',
        user: makeUser(['admin']),
        permissions: ['*']
      }
    } as unknown as LoginResult);
    await useAuthStore.getState().login({ username: 'u', password: 'p' });
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().token).toBe('t1');
    expect(sessionStorage.getItem('token')).toBe('t1');
    expect(sessionStorage.getItem('refresh_token')).toBe('r1');
  });

  it('login 失败抛错', async () => {
    loginMock.mockResolvedValue({
      success: false,
      message: 'bad'
    } as unknown as LoginResult);
    await expect(useAuthStore.getState().login({ username: 'u', password: 'p' })).rejects.toThrow(
      'bad'
    );
  });

  it('logout 有 token 时调用 apiLogout 并清理', async () => {
    useAuthStore.setState({ token: 't1', isAuthenticated: true });
    sessionStorage.setItem('token', 't1');
    await useAuthStore.getState().logout();
    expect(logoutMock).toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
  });

  it('logout 无 token 时不调用 apiLogout', async () => {
    useAuthStore.setState({ token: null, isAuthenticated: false });
    await useAuthStore.getState().logout();
    expect(logoutMock).not.toHaveBeenCalled();
  });

  it('clearAuth 清理 state + sessionStorage', () => {
    useAuthStore.setState({ token: 't1', isAuthenticated: true });
    sessionStorage.setItem('token', 't1');
    useAuthStore.getState().clearAuth();
    expect(useAuthStore.getState().token).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
  });

  it('checkAuth 依据 token + isAuthenticated', () => {
    useAuthStore.setState({ token: null, isAuthenticated: false });
    expect(useAuthStore.getState().checkAuth()).toBe(false);
    useAuthStore.setState({ token: 't1', isAuthenticated: true });
    expect(useAuthStore.getState().checkAuth()).toBe(true);
  });

  it('setAuth 写入 state + sessionStorage', () => {
    useAuthStore.getState().setAuth(makeUser([]), 't2', ['p']);
    expect(useAuthStore.getState().token).toBe('t2');
    expect(sessionStorage.getItem('token')).toBe('t2');
  });

  it('setVerifying 设置校验中状态', () => {
    useAuthStore.getState().setVerifying(true);
    expect(useAuthStore.getState().isVerifying).toBe(true);
  });
});
