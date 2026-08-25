/**
 * Sidebar 侧边栏
 *
 * 重构改动：
 * 1. filteredMenus 用 useMemo 包裹——原代码每次渲染都重新 filter，
 *    配合 usePermission 修复后 hasPermission 引用稳定，整体只在权限变化时重算
 * 2. menuItems 用 useMemo 包裹——每次展开/折叠侧边栏只重算 label 显隐，
 *    不做整个 filter + map 双重计算
 * 3. selectedKey 逻辑提取为独立变量，更易读
 * 4. menuConfigs 移到模块级别（已存在），避免重复定义
 */
import React, { useMemo } from 'react';
import { Menu, theme } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import { usePermission } from '@/hooks/usePermission';
import { useUIStore } from '@/stores/ui';
import { MENU_CONFIGS, FLATTENED_MENUS, findMenuByPath } from '@/constants/menu';


interface SidebarProps {
  collapsed: boolean;
}


const KEY_TO_PATH = new Map(FLATTENED_MENUS.map((m) => [m.key, m.path]));

function Sidebar({ collapsed }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasPermission } = usePermission();
  const { token } = theme.useToken(); 
  const addTab = useUIStore((s) => s.addTab);

  
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
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {}
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

      {}
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={handleMenuClick}
        style={{ border: 'none', flex: 1, overflowY: 'auto' }}
      />
    </div>
  );
}

export default Sidebar;
