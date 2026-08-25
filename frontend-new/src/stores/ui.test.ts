import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from './ui';

const HOME_TAB = { key: 'dashboard', title: '仪表盘', path: '/dashboard', closable: false };

beforeEach(() => {
  localStorage.clear();
  useUIStore.setState({
    theme: 'light',
    sidebarCollapsed: false,
    openTabs: [HOME_TAB],
    activeTabKey: 'dashboard'
  });
});

describe('useUIStore', () => {
  it('toggleTheme 切换明暗', () => {
    useUIStore.getState().toggleTheme();
    expect(useUIStore.getState().theme).toBe('dark');
    useUIStore.getState().toggleTheme();
    expect(useUIStore.getState().theme).toBe('light');
  });

  it('toggleSidebar 切换折叠', () => {
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
  });

  it('addTab 新增并激活', () => {
    useUIStore.getState().addTab({ key: 'a', title: 'A', path: '/a', closable: true });
    expect(useUIStore.getState().openTabs.length).toBe(2);
    expect(useUIStore.getState().activeTabKey).toBe('a');
  });

  it('addTab 已存在只激活不重复', () => {
    useUIStore
      .getState()
      .addTab({ key: 'dashboard', title: '仪表盘', path: '/dashboard', closable: false });
    expect(useUIStore.getState().openTabs.length).toBe(1);
    expect(useUIStore.getState().activeTabKey).toBe('dashboard');
  });

  it('removeTab 非激活页只删除', () => {
    useUIStore.getState().addTab({ key: 'a', title: 'A', path: '/a', closable: true });
    useUIStore.getState().addTab({ key: 'b', title: 'B', path: '/b', closable: true });
    useUIStore.getState().setActiveTab('a');
    useUIStore.getState().removeTab('b');
    expect(useUIStore.getState().openTabs.map((t) => t.key)).toEqual(['dashboard', 'a']);
    expect(useUIStore.getState().activeTabKey).toBe('a');
  });

  it('removeTab 激活页跳到相邻前一', () => {
    useUIStore.getState().addTab({ key: 'a', title: 'A', path: '/a', closable: true });
    useUIStore.getState().addTab({ key: 'b', title: 'B', path: '/b', closable: true });
    useUIStore.getState().setActiveTab('b');
    useUIStore.getState().removeTab('b');
    expect(useUIStore.getState().openTabs.map((t) => t.key)).toEqual(['dashboard', 'a']);
    expect(useUIStore.getState().activeTabKey).toBe('a');
  });

  it('removeTab 激活页跳到相邻后一', () => {
    useUIStore.getState().addTab({ key: 'a', title: 'A', path: '/a', closable: true });
    useUIStore.getState().addTab({ key: 'b', title: 'B', path: '/b', closable: true });
    useUIStore.getState().setActiveTab('a');
    useUIStore.getState().removeTab('a');
    expect(useUIStore.getState().openTabs.map((t) => t.key)).toEqual(['dashboard', 'b']);
    expect(useUIStore.getState().activeTabKey).toBe('b');
  });

  it('removeTab 不可关闭的常驻 tab 被保护', () => {
    useUIStore.getState().addTab({ key: 'a', title: 'A', path: '/a', closable: true });
    useUIStore.getState().setActiveTab('dashboard'); // 保持首页为激活态
    useUIStore.getState().removeTab('dashboard'); // 受保护，应被忽略，无变化
    expect(useUIStore.getState().openTabs.map((t) => t.key)).toEqual(['dashboard', 'a']);
    expect(useUIStore.getState().activeTabKey).toBe('dashboard');
  });

  it('setActiveTab 切换激活', () => {
    useUIStore.getState().setActiveTab('dashboard');
    expect(useUIStore.getState().activeTabKey).toBe('dashboard');
  });
});
