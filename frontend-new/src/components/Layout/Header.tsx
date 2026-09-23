/**
 * Header 顶栏
 * - 面包屑 + 主题切换 + 通知铃铛 + 用户信息 + 退出
 * - 纯展示组件：所有数据和回调均通过 Props 传入，不直接订阅任何 Store
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout, Button, Dropdown, Avatar, Space, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  UserOutlined,
  BulbOutlined,
  SettingOutlined,
  TranslationOutlined,
} from '@ant-design/icons';
import type { User } from '@/types/models';
import NotificationBell from '@/components/Notification/NotificationBell';
import { changeLanguage } from '@/i18n';
import { SUPPORTED_LANGUAGES, type AppLanguage } from '@/i18n/config';

interface HeaderProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  user: User | null;
  onLogout: () => void;
  isMobile?: boolean;
}

const { Header: AntHeader } = Layout;

function Header({
  sidebarCollapsed,
  onToggleSidebar,
  theme: themeMode,
  onToggleTheme,
  user,
  onLogout,
  isMobile = false
}: HeaderProps) {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { t: tAuth } = useTranslation('auth');

  const currentLang = (i18n.resolvedLanguage || i18n.language) as AppLanguage;
  const currentLangMeta =
    SUPPORTED_LANGUAGES.find((l) => l.key === currentLang) ?? SUPPORTED_LANGUAGES[0];
  const nextLang = SUPPORTED_LANGUAGES.find((l) => l.key !== currentLang)?.key ?? 'zh-CN';

  const userMenuItems = [
    ...(isMobile
      ? [
          {
            key: 'theme',
            icon: <BulbOutlined />,
            label: themeMode === 'light' ? t('theme.switchDark') : t('theme.switchLight'),
            onClick: onToggleTheme,
          },
          { key: 'divider-theme', type: 'divider' as const },
          {
            key: 'language',
            icon: <TranslationOutlined />,
            label: t('language.switchTo'),
            onClick: () => changeLanguage(nextLang),
          },
          { key: 'divider-language', type: 'divider' as const },
        ]
      : []),
    {
      key: 'profile',
      icon: <SettingOutlined />,
      label: t('user.profile'),
      onClick: () => navigate('/profile'),
    },
    {
      key: 'divider-account',
      type: 'divider' as const
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: tAuth('action.logout'),
      onClick: onLogout,
    },
  ];

  return (
    <AntHeader
      style={{
        padding: isMobile ? '0 12px' : '0 24px',
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
      <Space size={isMobile ? 'small' : 'middle'}>
        <NotificationBell />
        {!isMobile && (
          <Button
            type="text"
            icon={<BulbOutlined />}
            onClick={onToggleTheme}
            title={themeMode === 'light' ? t('theme.switchDark') : t('theme.switchLight')}
          />
        )}
        {!isMobile && (
          <Button
            type="text"
            icon={<TranslationOutlined />}
            onClick={() => changeLanguage(nextLang)}
            title={t('language.switchTo')}
            aria-label={t('language.switchTo')}
          >
            {currentLangMeta.short}
          </Button>
        )}
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }} size={4}>
            <Avatar size="small" icon={<UserOutlined />} />
            {!isMobile && <span>{user?.username ?? t('user.notLoggedIn')}</span>}
          </Space>
        </Dropdown>
      </Space>
    </AntHeader>
  );
}

export default Header;
