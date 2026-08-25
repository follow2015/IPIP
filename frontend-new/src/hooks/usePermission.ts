/**
 * 权限 Hook
 *
 * 重构改动：
 * 1. 三个函数统一用 useCallback 包裹——否则每次渲染都生成新引用，
 *    导致依赖它们的子组件（React.memo / useMemo）无谓重渲染
 * 2. 用细粒度 selector 订阅 store，避免任何 store 字段变化都触发渲染：
 *    - 只订阅 permissions 数组
 *    - 只订阅 user.roles 数组
 */
import { useCallback } from 'react';
import { useAuthStore } from '@/stores/auth';


export interface UsePermissionReturn {
  
  hasPermission: (permission: string) => boolean;
  
  hasAnyPermission: (permissions: string[]) => boolean;
  
  hasAllPermissions: (permissions: string[]) => boolean;
  
  hasRole: (role: string) => boolean;
}


export function usePermission(): UsePermissionReturn {
  
  const permissions = useAuthStore((s) => s.permissions);
  const userRoles   = useAuthStore((s) => s.user?.roles);

  const hasPermission = useCallback(
    (permission: string) =>
      permissions.includes('*') || permissions.includes(permission),
    [permissions],
  );

  const hasAnyPermission = useCallback(
    (perms: string[]) => perms.some(hasPermission),
    [hasPermission],
  );

  const hasAllPermissions = useCallback(
    (perms: string[]) => perms.every(hasPermission),
    [hasPermission],
  );

  const hasRole = useCallback(
    (role: string) => userRoles?.includes(role) ?? false,
    [userRoles],
  );

  return { hasPermission, hasAnyPermission, hasAllPermissions, hasRole };
}
