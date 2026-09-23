import { useMemo, useEffect } from 'react';
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider, theme, message } from 'antd';
import { useTranslation } from 'react-i18next';
import i18next, { ANTD_LOCALE } from '@/i18n';
import type { AppLanguage } from '@/i18n/config';
import AppRouter from '@/router';
import ErrorBoundary from '@/components/ErrorBoundary';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useUIStore } from '@/stores/ui';

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return i18next.t('message.requestFailed');
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
  const { i18n } = useTranslation();

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

  const currentLang = (i18n.resolvedLanguage || i18n.language) as AppLanguage;
  const antdLocale = ANTD_LOCALE[currentLang] ?? ANTD_LOCALE['zh-CN'];

  useEffect(() => {
    ConfigProvider.config({ theme: themeConfig });
  }, [themeConfig]);

  return (
    <ErrorBoundary>
      <ConfigProvider theme={themeConfig} locale={antdLocale}>
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
