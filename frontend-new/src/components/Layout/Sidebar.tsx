import React, { useMemo } from 'react';
import { Menu, theme, Tooltip } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import { usePermission } from '@/hooks/usePermission';
import { useAppVersion } from '@/hooks/useAppVersion';
import { useUIStore } from '@/stores/ui';
import { MENU_CONFIGS, FLATTENED_MENUS, findMenuByPath } from '@/constants/menu';

interface SidebarProps {
  collapsed: boolean;
  onNavigate?: () => void;
}

const KEY_TO_PATH = new Map(FLATTENED_MENUS.map((m) => [m.key, m.path]));

function Sidebar({ collapsed, onNavigate }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasPermission } = usePermission();
  const { token } = theme.useToken(); // 已 useCallback 包裹，引用稳定
  const addTab = useUIStore((s) => s.addTab);
  const version = useAppVersion();

  const filteredMenus = useMemo(
    () => MENU_CONFIGS.filter((item) => !item.permission || hasPermission(item.permission)),
    [hasPermission]
  );

  const menuItems = useMemo(
    () =>
      filteredMenus.map((item) => {
        if (item.children && item.children.length > 0) {
          const childItems = item.children
            .filter((c) => !c.permission || hasPermission(c.permission))
            .map((c) => ({
              key: c.key,
              icon: c.icon,
              label: collapsed ? null : c.label,
              title: c.label
            }));
          return {
            key: item.key,
            icon: item.icon,
            label: collapsed ? null : item.label,
            title: item.label,
            children: childItems
          };
        }
        return {
          key: item.key,
          icon: item.icon,
          label: collapsed ? null : item.label,
          title: item.label
        };
      }),
    [filteredMenus, collapsed, hasPermission]
  );

  const selectedKey = useMemo(() => {
    const matched = findMenuByPath(location.pathname);
    return matched?.key ?? 'dashboard';
  }, [location.pathname]);

  const handleMenuClick = ({ key }: { key: string }) => {
    const path = KEY_TO_PATH.get(key);
    if (path) {
      const config = FLATTENED_MENUS.find((m) => m.key === key);
      if (config) {
        addTab({
          key: config.key,
          title: config.label,
          path: config.path,
          closable: key !== 'dashboard'
        });
      }
      navigate(path);
      onNavigate?.();
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Logo */}
      <div
        style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          overflow: 'hidden'
        }}
      >
        <h2 style={{ margin: 0, fontSize: collapsed ? 14 : 18, whiteSpace: 'nowrap' }}>
          {collapsed ? 'IP' : 'IPIP 管理系统'}
        </h2>
      </div>

      {/* 导航菜单 */}
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={handleMenuClick}
        style={{ border: 'none', flex: 1, overflowY: 'auto' }}
      />

      {/* 版本号：常驻可见，便于报障时快速核对线上版本；折叠态只留版本号 */}
      {version && (
        <Tooltip title={`后端版本 v${version}`} placement="right">
          <div
            data-testid="sidebar-version"
            style={{
              flexShrink: 0,
              padding: '8px 12px 10px',
              borderTop: `1px solid ${token.colorBorderSecondary}`,
              textAlign: 'center',
              fontSize: 12,
              lineHeight: '18px',
              color: token.colorTextTertiary,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              cursor: 'default'
            }}
          >
            {collapsed ? `v${version}` : `版本 v${version}`}
          </div>
        </Tooltip>
      )}
    </div>
  );
}

export default Sidebar;
