/**
 * 路由守卫组件
 * - PrivateRoute: 检查认证状态，未登录重定向 /login
 * - PermissionRoute: 检查权限，无权限显示 403
 */
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuthStore } from '@/stores/auth';
import { usePermission } from '@/hooks/usePermission';
import { useTranslation } from 'react-i18next';

interface PrivateRouteProps {
  children: React.ReactNode;
}

/**
 * 认证守卫：未登录时重定向到 /login
 * token 验证期间显示 loading，避免短暂闪现后踢出
 */
export const PrivateRoute: React.FC<PrivateRouteProps> = ({ children }) => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isVerifying = useAuthStore((s) => s.isVerifying);
  const location = useLocation();
  const { t } = useTranslation('common');

  if (isVerifying) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" description={t('error.verifyingAuth')} />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

interface PermissionRouteProps {
  requiredPermission: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * 权限守卫：无指定权限时显示 403
 */
export const PermissionRoute: React.FC<PermissionRouteProps> = ({
  requiredPermission,
  children,
  fallback,
}) => {
  const { hasPermission } = usePermission();
  const { t } = useTranslation('common');

  if (!hasPermission(requiredPermission)) {
    return (
      fallback ?? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <h1>403</h1>
          <p>{t('error.noPermission')}</p>
        </div>
      )
    );
  }

  return <>{children}</>;
};
