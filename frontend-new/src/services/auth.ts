/**
 * 认证服务
 * - login: 用户登录
 * - logout: 用户登出
 * - verifyToken: 验证 Token 有效性
 * - refreshToken: 刷新 Token
 * 对齐后端 /api/auth/* 端点
 */
import { post, get } from './api-client';
import type { LoginRequest, LoginResponse } from '@/types/api';


export async function login(credentials: LoginRequest) {
  return post<LoginResponse>('/auth/login', credentials);
}


export async function logout() {
  return post<null>('/auth/logout');
}


export async function verifyToken() {
  return get<{ id: number; username: string; email: string; roles: string[]; is_active: boolean }>('/auth/profile');
}


export async function refreshToken(refreshTokenValue: string) {
  return post<{ token: string; refresh_token: string }>('/users/refresh', { refresh_token: refreshTokenValue });
}
