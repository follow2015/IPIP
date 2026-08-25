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


interface PrivateRouteProps {
  children: React.ReactNode;
}


export const PrivateRoute: React.FC<PrivateRouteProps> = ({ children }) => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isVerifying = useAuthStore((s) => s.isVerifying);
  const location = useLocation();

  if (isVerifying) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" description="验证登录状态..." />
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


export const PermissionRoute: React.FC<PermissionRouteProps> = ({
  requiredPermission,
  children,
  fallback,
}) => {
  const { hasPermission } = usePermission();

  if (!hasPermission(requiredPermission)) {
    return (
      fallback ?? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <h1>403</h1>
          <p>抱歉，您没有访问此页面的权限</p>
        </div>
      )
    );
  }

  return <>{children}</>;
};
