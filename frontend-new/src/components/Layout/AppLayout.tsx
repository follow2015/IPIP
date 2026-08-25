/**
 * AppLayout 整体布局
 * - Sider + Header + Content + Tabs
 * - AppLayout 作为 UI 状态的唯一订阅者，通过 Props 传递给子组件
 * - 子组件成为纯展示组件，易于测试和 Storybook 文档化
 */
import React, { useEffect } from 'react';
import { Layout, theme } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import TabBar from './TabBar';
import { useUIStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';
import { useGlobalEvents } from '@/hooks/useGlobalEvents';
import { findMenuByPath } from '@/constants/menu';

const { Sider, Content } = Layout;


function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar    = useUIStore((s) => s.toggleSidebar);
  const themeMode        = useUIStore((s) => s.theme);
  const toggleTheme      = useUIStore((s) => s.toggleTheme);
  const openTabs         = useUIStore((s) => s.openTabs);
  const activeTabKey     = useUIStore((s) => s.activeTabKey);
  const addTab           = useUIStore((s) => s.addTab);
  const removeTab        = useUIStore((s) => s.removeTab);
  const setActiveTab     = useUIStore((s) => s.setActiveTab);

  const user             = useAuthStore((s) => s.user);
  const logout           = useAuthStore((s) => s.logout);

  
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  useGlobalEvents({ enabled: isAuthenticated });

  
  useEffect(() => {
    const menu = findMenuByPath(location.pathname);
    if (menu) {
      addTab({ key: menu.key, title: menu.label, path: menu.path, closable: menu.key !== 'dashboard' });
    }
  }, [location.pathname, addTab]);

  
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={sidebarCollapsed}
        width={220}
        theme="light"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Sidebar collapsed={sidebarCollapsed} />
      </Sider>
      <Layout style={{ marginLeft: sidebarCollapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>
        <Header
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          theme={themeMode}
          onToggleTheme={toggleTheme}
          user={user}
          onLogout={handleLogout}
        />
        <TabBar
          openTabs={openTabs}
          activeTabKey={activeTabKey}
          onRemoveTab={removeTab}
          onSetActiveTab={setActiveTab}
        />
        <Content style={{ margin: 16, padding: 24, background: token.colorBgContainer, borderRadius: 8, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

export default AppLayout;
