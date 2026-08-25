/**
 * UI 状态 store
 * - 主题 / 侧边栏折叠 / 多标签页 + localStorage 持久化
 *
 * 重构改动——UX Bug 修复：
 *
 * 原 removeTab：关闭当前激活的标签页时，总跳到最后一个标签页：
 *   tabs[tabs.length - 1]?.key ?? 'dashboard'
 *
 * 问题：用户视角下，关闭当前页应跳到相邻页（右侧优先，与浏览器/IDE 标签页
 * 行为一致：Chrome / VS Code / Firefox 关闭标签后焦点落到右侧相邻标签），
 * 而非无论在哪关闭都跳到末尾。
 *
 * 修复：找到被关闭 tab 的位置，优先跳转到后一个，否则前一个。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface TabInfo {
  key: string;
  title: string;
  path: string;
  closable: boolean;
}

interface UIState {
  theme: 'light' | 'dark';
  sidebarCollapsed: boolean;
  openTabs: TabInfo[];
  activeTabKey: string;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  addTab: (tab: TabInfo) => void;
  removeTab: (key: string) => void;
  setActiveTab: (key: string) => void;
}

const HOME_TAB: TabInfo = {
  key: 'dashboard',
  title: '仪表盘',
  path: '/dashboard',
  closable: false
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarCollapsed: false,
      openTabs: [HOME_TAB],
      activeTabKey: 'dashboard',

      toggleTheme: () => set((s) => ({ theme: s.theme === 'light' ? 'dark' : 'light' })),

      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

      addTab: (tab) =>
        set((s) => {
          if (s.openTabs.some((t) => t.key === tab.key)) {
            return { activeTabKey: tab.key };
          }
          return { openTabs: [...s.openTabs, tab], activeTabKey: tab.key };
        }),

      removeTab: (key) =>
        set((s) => {
          const target = s.openTabs.find((t) => t.key === key);
          if (target && target.closable === false) {
            return {};
          }
          const idx = s.openTabs.findIndex((t) => t.key === key);
          const tabs = s.openTabs.filter((t) => t.key !== key);

          if (s.activeTabKey !== key) {
            return { openTabs: tabs };
          }

          const adjacent = s.openTabs[idx + 1] ?? s.openTabs[idx - 1];
          const activeTabKey = adjacent?.key ?? HOME_TAB.key;
          return { openTabs: tabs, activeTabKey };
        }),

      setActiveTab: (key) => set({ activeTabKey: key })
    }),
    {
      name: 'ui-storage',
      partialize: (s) => ({
        theme: s.theme,
        sidebarCollapsed: s.sidebarCollapsed
      })
    }
  )
);
