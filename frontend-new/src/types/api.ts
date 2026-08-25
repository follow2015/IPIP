/**
 * API 统一响应类型定义
 * 对接后端 Flask API 响应格式
 */


export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error_code: string | null;
  timestamp: string;
}


export interface BackendPaginatedData<T> {
  data: T[];
  pagination: {
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
  };
}


export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}


export interface PaginationParams {
  page?: number;
  per_page?: number;
  search?: string;
  [key: string]: unknown;
}


export interface LoginRequest {
  username: string;
  password: string;
}


export interface LoginResponse {
  token: string;                    
  refresh_token: string;
  user: {
    id: number;
    username: string;
    email: string | null;
    name?: string;
    real_name?: string;
    roles: string[];                
    is_active: boolean;
    status: number;
  };
  permissions: string[];            
  expires_in: number;
}


export function adaptPaginatedResponse<T>(
  backend: BackendPaginatedData<T>,
): PaginatedData<T> {
  return {
    items: backend.data,
    total: backend.pagination.total,
    page: backend.pagination.page,
    per_page: backend.pagination.per_page,
    total_pages: backend.pagination.total_pages,
  };
}
