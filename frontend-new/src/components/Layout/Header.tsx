/**
 * Header 顶栏
 * - 面包屑 + 主题切换 + 通知铃铛 + 用户信息 + 退出
 * - 纯展示组件：所有数据和回调均通过 Props 传入，不直接订阅任何 Store
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout, Button, Dropdown, Avatar, Space, theme } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  UserOutlined,
  BulbOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { User } from '@/types/models';
import NotificationBell from '@/components/Notification/NotificationBell';

interface HeaderProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  user: User | null;
  onLogout: () => void;
}

const { Header: AntHeader } = Layout;


function Header({ sidebarCollapsed, onToggleSidebar, theme: themeMode, onToggleTheme, user, onLogout }: HeaderProps) {
  const { token } = theme.useToken();
  const navigate = useNavigate();

  
  const userMenuItems = [
    {
      key: 'profile',
      icon: <SettingOutlined />,
      label: '用户中心',
      onClick: () => navigate('/profile'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: onLogout,
    },
  ];

  return (
    <AntHeader
      style={{
        padding: '0 24px',
        background: token.colorBgContainer,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        position: 'sticky',
        top: 0,
        zIndex: 1,
      }}
    >
      <Space>
        <Button
          type="text"
          icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={onToggleSidebar}
        />
      </Space>
      <Space size="middle">
        <NotificationBell />
        <Button
          type="text"
          icon={<BulbOutlined />}
          onClick={onToggleTheme}
          title={themeMode === 'light' ? '切换深色模式' : '切换浅色模式'}
        />
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} />
            <span>{user?.username ?? '未登录'}</span>
          </Space>
        </Dropdown>
      </Space>
    </AntHeader>
  );
}

export default Header;
