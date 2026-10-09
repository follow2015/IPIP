import { useMemo, useEffect, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider, theme } from 'antd';
import { grafanaDarkAlgorithm, GRAFANA_DARK_SEED } from '@/theme/grafanaDark';
import { useTranslation } from 'react-i18next';
import i18next, { ANTD_LOCALE } from '@/i18n';
import type { AppLanguage } from '@/i18n/config';
import AppRouter from '@/router';
import ErrorBoundary from '@/components/ErrorBoundary';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useUIStore } from '@/stores/ui';
import { useResponsive } from '@/hooks/useResponsive';

const MOBILE_TOUCH_TOKEN = { controlHeight: 44, controlHeightSM: 44 };
const MOBILE_TOUCH_COMPONENTS = {
  Select: { optionHeight: 44 },
  Pagination: { itemSize: 44 }
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return i18next.t('message.requestFailed');
}

type MessageInstance = ReturnType<typeof AntApp.useApp>['message'];
let globalMessage: MessageInstance | null = null;

const queryCache = new QueryCache({
  onError: (error, query) => {
    if (!query.state.data) {
      globalMessage?.error(getErrorMessage(error));
    }
  }
});

const mutationCache = new MutationCache({
  onError: (error) => {
    globalMessage?.error(getErrorMessage(error));
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

function GlobalMessageBridge({ children }: { children: ReactNode }) {
  const { message } = AntApp.useApp();
  globalMessage = message;
  return <>{children}</>;
}

function App() {
  useAuthInit();

  const themeMode = useUIStore((s) => s.theme);
  const { i18n } = useTranslation();
  const { isMobile } = useResponsive();

  const themeConfig = useMemo(
    () => ({
      token: {
        colorPrimary: '#1677ff',
        borderRadius: 6,
        ...(themeMode === 'dark' ? GRAFANA_DARK_SEED : {}),
        ...(isMobile ? MOBILE_TOUCH_TOKEN : {})
      },
      ...(isMobile ? { components: MOBILE_TOUCH_COMPONENTS } : {}),
      algorithm: themeMode === 'dark' ? grafanaDarkAlgorithm : theme.defaultAlgorithm
    }),
    [themeMode, isMobile]
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
          <GlobalMessageBridge>
            <QueryClientProvider client={queryClient}>
              <AppRouter />
            </QueryClientProvider>
          </GlobalMessageBridge>
        </AntApp>
      </ConfigProvider>
    </ErrorBoundary>
  );
}

export default App;
