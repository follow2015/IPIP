/**
 * TabBar 多标签页组件
 * - 支持打开/关闭/切换标签页
 * - 接收 Props 而非直接订阅 useUIStore，成为纯展示组件
 */
import React from 'react';
import { Tabs, theme } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { TabInfo } from '@/stores/ui';

interface TabBarProps {
  openTabs: TabInfo[];
  activeTabKey: string;
  onRemoveTab: (key: string) => void;
  onSetActiveTab: (key: string) => void;
}

function TabBar({ openTabs, activeTabKey, onRemoveTab, onSetActiveTab }: TabBarProps) {
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const handleTabChange = (key: string) => {
    onSetActiveTab(key);
    const tab = openTabs.find((t) => t.key === key);
    if (tab) {
      navigate(tab.path);
    }
  };

  const handleTabEdit = (
    targetKey: string | React.MouseEvent | React.KeyboardEvent,
    action: 'add' | 'remove',
  ) => {
    if (action === 'remove' && typeof targetKey === 'string') {
      const tab = openTabs.find((t) => t.key === targetKey);
      if (tab && tab.closable) {
        onRemoveTab(targetKey);
      }
    }
  };

  return (
    <Tabs
      type="editable-card"
      hideAdd
      activeKey={activeTabKey}
      onChange={handleTabChange}
      onEdit={handleTabEdit}
      items={openTabs.map((tab) => ({
        key: tab.key,
        label: tab.title,
        closable: tab.closable,
      }))}
      style={{ padding: '8px 16px 0', background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}` }}
    />
  );
}

export default TabBar;
