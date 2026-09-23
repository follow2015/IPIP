import axios, {
  AxiosError,
  InternalAxiosRequestConfig,
  type AxiosResponse,
  type AxiosRequestConfig
} from 'axios';
import i18next from 'i18next';
import type { ApiResponse, ApiResponseMaybe, BackendPaginatedData } from '@/types/api';
import { adaptPaginatedResponse } from '@/types/api';

interface ApiErrorData {
  message?: string;
  error_code?: string;
  details?: unknown;
  i18n_key?: string;
  params?: Record<string, unknown>;
  response?: AxiosResponse;
}

let backendNsPromise: Promise<void> | null = null;

function ensureBackendNs(): Promise<void> {
  if (!backendNsPromise) {
    backendNsPromise = (async () => {
      const [{ default: i18n }, zh, en] = await Promise.all([
        import('@/i18n'),
        import('@/locales/zh-CN/backend.json'),
        import('@/locales/en-US/backend.json')
      ]);
      i18n.addResourceBundle('zh-CN', 'backend', zh, true, true);
      i18n.addResourceBundle('en-US', 'backend', en, true, true);
    })().catch((err) => {
      backendNsPromise = null; // 失败就允许下次重试
      throw err;
    });
  }
  return backendNsPromise;
}

async function localizeBackendError(
  errorData: ApiErrorData | undefined,
  fallback: string | undefined
): Promise<string | undefined> {
  const i18nKey = errorData?.i18n_key;
  if (!i18nKey) return fallback;
  try {
    const [{ default: i18n }] = await Promise.all([import('@/i18n'), ensureBackendNs()]);
    const translate = i18n.t as unknown as (
      key: string,
      options?: Record<string, unknown>
    ) => string;
    const params =
      errorData?.params && typeof errorData.params === 'object' ? errorData.params : {};
    return translate(i18nKey, { ...params, defaultValue: fallback ?? '' }) || fallback;
  } catch {
    return fallback;
  }
}

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000, // CR-19: 全局默认 30 秒，扫描等长操作单独设更长超时
  withCredentials: false
});


apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = sessionStorage.getItem('token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);


let isRefreshing = false;
let pendingRequests: Array<(err?: Error) => void> = [];

function resolvePendingRequests(): void {
  const waiters = pendingRequests;
  pendingRequests = [];
  waiters.forEach((cb) => cb());
}

function rejectPendingRequests(err: Error): void {
  const waiters = pendingRequests;
  pendingRequests = [];
  waiters.forEach((cb) => cb(err));
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = sessionStorage.getItem('refresh_token');
  if (!refreshToken) return null;

  try {
    const res = await axios.post<ApiResponse<{ token: string; refresh_token: string }>>(
      '/api/users/refresh',
      { refresh_token: refreshToken }
    );
    if (!res.data?.success || !res.data?.data) return null;

    const { token, refresh_token } = res.data.data;
    sessionStorage.setItem('token', token);
    sessionStorage.setItem('refresh_token', refresh_token);
    try {
      const { useAuthStore } = await import('@/stores/auth');
      const state = useAuthStore.getState();
      if (state.isAuthenticated) {
        useAuthStore.setState({ token });
      }
    } catch {
      /* store 不可用时降级，sessionStorage 已更新 */
    }
    return token;
  } catch {
    return null;
  }
}


apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data as ApiResponse<unknown>;

    if (
      res.data &&
      typeof res.data === 'object' &&
      'pagination' in (res.data as object) &&
      'data' in (res.data as object) &&
      Array.isArray((res.data as Record<string, unknown>).data)
    ) {
      res.data = adaptPaginatedResponse(res.data as BackendPaginatedData<unknown>);
    }

    response.data = res;
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      const url = originalRequest?.url ?? '';
      const isAuthEndpoint =
        url.startsWith('/auth/login') ||
        url.startsWith('/auth/register') ||
        url.startsWith('/auth/logout') ||
        url.startsWith('/auth/profile') ||
        url.startsWith('/users/refresh');

      if (!isAuthEndpoint) {
        const refreshToken = sessionStorage.getItem('refresh_token');
        if (refreshToken) {
          if (!isRefreshing) {
            isRefreshing = true;
            let newToken: string | null = null;
            let refreshFailure: Error | null = null;
            try {
              newToken = await refreshAccessToken();
            } catch {
              refreshFailure = new Error(i18next.t('message.tokenRefreshFailed', { ns: 'auth' }));
            } finally {
              isRefreshing = false;
            }

            if (newToken) {
              resolvePendingRequests();

              originalRequest._retry = true;
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
              return apiClient(originalRequest);
            }

            const refreshErr =
              refreshFailure ?? new Error(i18next.t('message.tokenRefreshFailed', { ns: 'auth' }));
            rejectPendingRequests(refreshErr);
            handleUnauthorized();
            return Promise.reject(refreshErr);
          }

          return new Promise((resolve, reject) => {
            pendingRequests.push((err?: Error) => {
              if (err) {
                reject(err);
                return;
              }
              originalRequest._retry = true;
              const currentToken = sessionStorage.getItem('token');
              if (currentToken) {
                originalRequest.headers.Authorization = `Bearer ${currentToken}`;
              }
              resolve(apiClient(originalRequest));
            });
          });
        }

        handleUnauthorized();
      }
    }

    const errorData = error.response?.data as ApiErrorData | undefined;
    const backendMsg = errorData?.message;
    const message = await localizeBackendError(
      errorData,
      typeof backendMsg === 'string' ? backendMsg : undefined
    );
    if (message) {
      const enhanced = new Error(message);
      enhanced.name = `Http${error.response?.status ?? 'Error'}`;
      (enhanced as ApiErrorData & Error).response = error.response;
      return Promise.reject(enhanced);
    }
    return Promise.reject(error);
  }
);


let isHandling401 = false;

/**
 * 处理 401 未授权响应
 * - 防并发：2秒内只处理一次
 * - 防误清：动态 import 期间用户可能已重新登录，需比对 token 是否仍为触发 401 时的旧值
 * - 使用 clearAuth() 而非 logout()：token 已被后端拒绝，无需再发 /auth/logout 撤销
 */
function handleUnauthorized(): void {
  if (isHandling401) return;
  isHandling401 = true;

  const staleToken = sessionStorage.getItem('token');

  import('@/stores/auth').then(({ useAuthStore }) => {
    const currentToken = sessionStorage.getItem('token');
    if (currentToken !== staleToken) return;
    useAuthStore.getState().clearAuth();
    import('@/router')
      .then(({ router }) => {
        router.navigate('/login');
      })
      .catch(() => {
        window.location.href = '/login';
      });
  });

  setTimeout(() => {
    isHandling401 = false;
  }, 5_000);
}


export async function get<T>(
  url: string,
  params?: Record<string, unknown>,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> {
  const res = await apiClient.get<ApiResponse<T>>(url, { params, ...config });
  return res.data;
}

export async function getMaybe<T>(
  url: string,
  params?: Record<string, unknown>,
  config?: AxiosRequestConfig
): Promise<ApiResponseMaybe<T>> {
  const res = await apiClient.get<ApiResponseMaybe<T>>(url, { params, ...config });
  return res.data;
}

export async function post<T, D extends object = object>(
  url: string,
  data?: D,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> {
  const res = await apiClient.post<ApiResponse<T>>(
    url,
    data as unknown as Record<string, unknown>,
    config
  );
  return res.data;
}

export async function put<T, D extends object = object>(
  url: string,
  data?: D,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> {
  const res = await apiClient.put<ApiResponse<T>>(
    url,
    data as unknown as Record<string, unknown>,
    config
  );
  return res.data;
}

export async function patch<T, D extends object = object>(
  url: string,
  data?: D,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> {
  const res = await apiClient.patch<ApiResponse<T>>(
    url,
    data as unknown as Record<string, unknown>,
    config
  );
  return res.data;
}

export async function del<T, D extends object = object>(
  url: string,
  data?: D,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> {
  const res = await apiClient.delete<ApiResponse<T>>(url, { data, ...config });
  return res.data;
}

export default apiClient;
