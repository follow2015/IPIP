/**
 * Axios 实例 + 请求/响应拦截器
 *
 * 改动说明（重构）：
 * - post / put 的 data 参数改为泛型 D extends object，消除调用方 33 处 `as unknown as` 强制转换
 * - handleUnauthorized 防重入逻辑不变，注释更清晰
 * - Token 自动刷新：401 时尝试用 refresh_token 换新 access_token
 * - 消除 as any：使用 ApiErrorData 接口替代
 */
import axios, { AxiosError, InternalAxiosRequestConfig, type AxiosResponse } from 'axios';
import type { ApiResponse, BackendPaginatedData } from '@/types/api';
import { adaptPaginatedResponse } from '@/types/api';


interface ApiErrorData {
  message?: string;
  error_code?: string;
  details?: unknown;
  response?: AxiosResponse;
}

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000, 
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
            try {
              const newToken = await refreshAccessToken();
              isRefreshing = false;

              if (newToken) {
                
                pendingRequests.forEach((cb) => cb());
                pendingRequests = [];

                originalRequest._retry = true;
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return apiClient(originalRequest);
              } else {
                
                const refreshErr = new Error('Token 刷新失败，请重新登录');
                pendingRequests.forEach((cb) => cb(refreshErr));
                pendingRequests = [];
                handleUnauthorized();
              }
            } catch {
              isRefreshing = false;
              
              const refreshErr = new Error('Token 刷新异常，请重新登录');
              pendingRequests.forEach((cb) => cb(refreshErr));
              pendingRequests = [];
              handleUnauthorized();
            }
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
    if (backendMsg && typeof backendMsg === 'string') {
      const enhanced = new Error(backendMsg);
      enhanced.name = `Http${error.response?.status ?? 'Error'}`;
      (enhanced as ApiErrorData & Error).response = error.response;
      return Promise.reject(enhanced);
    }
    return Promise.reject(error);
  }
);


let isHandling401 = false;


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
  params?: Record<string, unknown>
): Promise<ApiResponse<T>> {
  const res = await apiClient.get<ApiResponse<T>>(url, { params });
  return res.data;
}


export async function post<T, D extends object = object>(
  url: string,
  data?: D
): Promise<ApiResponse<T>> {
  const res = await apiClient.post<ApiResponse<T>>(url, data as unknown as Record<string, unknown>);
  return res.data;
}


export async function put<T, D extends object = object>(
  url: string,
  data?: D
): Promise<ApiResponse<T>> {
  const res = await apiClient.put<ApiResponse<T>>(url, data as unknown as Record<string, unknown>);
  return res.data;
}


export async function patch<T, D extends object = object>(
  url: string,
  data?: D
): Promise<ApiResponse<T>> {
  const res = await apiClient.patch<ApiResponse<T>>(
    url,
    data as unknown as Record<string, unknown>
  );
  return res.data;
}


export async function del<T, D extends object = object>(
  url: string,
  data?: D
): Promise<ApiResponse<T>> {
  const res = await apiClient.delete<ApiResponse<T>>(url, data ? { data } : undefined);
  return res.data;
}

export default apiClient;
