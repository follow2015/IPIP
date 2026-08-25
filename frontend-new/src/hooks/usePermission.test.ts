import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePermission } from './usePermission';
import { useAuthStore } from '@/stores/auth';
import type { User } from '@/types/models';

beforeEach(() => {
  useAuthStore.setState({
    user: null,
    token: null,
    permissions: [],
    isAuthenticated: false,
    isVerifying: false
  });
});

function setUser(roles: string[]) {
  useAuthStore.setState({
    user: {
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
    } as unknown as User
  });
}

describe('usePermission', () => {
  it("hasPermission '*' 视为超级权限", () => {
    useAuthStore.setState({ permissions: ['*'] });
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasPermission('device:write')).toBe(true);
  });

  it('hasPermission 精确匹配', () => {
    useAuthStore.setState({ permissions: ['device:read'] });
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasPermission('device:read')).toBe(true);
    expect(result.current.hasPermission('device:write')).toBe(false);
  });

  it('hasAnyPermission OR 关系', () => {
    useAuthStore.setState({ permissions: ['a'] });
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasAnyPermission(['x', 'a'])).toBe(true);
    expect(result.current.hasAnyPermission(['x', 'y'])).toBe(false);
  });

  it('hasAllPermissions AND 关系', () => {
    useAuthStore.setState({ permissions: ['a', 'b'] });
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasAllPermissions(['a', 'b'])).toBe(true);
    expect(result.current.hasAllPermissions(['a', 'c'])).toBe(false);
  });

  it('hasRole 按 user.roles 判定', () => {
    setUser(['admin']);
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasRole('admin')).toBe(true);
    expect(result.current.hasRole('user')).toBe(false);
  });

  it('hasRole 无 user 时返回 false', () => {
    useAuthStore.setState({ user: null });
    const { result } = renderHook(() => usePermission());
    expect(result.current.hasRole('admin')).toBe(false);
  });
});
