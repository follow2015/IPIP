/**
 * 根组件
 * - ConfigProvider（Ant Design 主题 + 中文 locale）
 * - QueryClientProvider（TanStack Query 全局配置）
 * - AppRouter（路由）
 */
import { useMemo, useEffect } from 'react';
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider, theme, message } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppRouter from '@/router';
import ErrorBoundary from '@/components/ErrorBoundary';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useUIStore } from '@/stores/ui';

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return '请求失败，请稍后重试';
}

const queryCache = new QueryCache({
  onError: (error, query) => {
    if (!query.state.data) {
      message.error(getErrorMessage(error));
    }
  }
});

const mutationCache = new MutationCache({
  onError: (error) => {
    message.error(getErrorMessage(error));
  }
});

const queryClient = new QueryClient({
  queryCache,
  mutationCache,
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: true
    }
  }
});

function App() {
  useAuthInit();

  const themeMode = useUIStore((s) => s.theme);

  const themeConfig = useMemo(
    () => ({
      token: {
        colorPrimary: '#1677ff',
        borderRadius: 6
      },
      algorithm: themeMode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm
    }),
    [themeMode]
  );

  useEffect(() => {
    ConfigProvider.config({ theme: themeConfig });
  }, [themeConfig]);

  return (
    <ErrorBoundary>
      <ConfigProvider theme={themeConfig} locale={zhCN}>
        <AntApp>
          <QueryClientProvider client={queryClient}>
            <AppRouter />
          </QueryClientProvider>
        </AntApp>
      </ConfigProvider>
    </ErrorBoundary>
  );
}

export default App;
