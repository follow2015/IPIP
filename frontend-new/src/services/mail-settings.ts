/**
 * 邮件服务器配置 API hooks
 *
 * GET    /api/settings/mail      — 管理员读取 SMTP 配置
 * PUT    /api/settings/mail      — 管理员更新 SMTP 配置
 * DELETE /api/settings/mail      — 管理员删除 SMTP 配置
 * POST   /api/settings/mail/test — 测试邮件服务器连通性
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put, post, del } from '@/services/api-client';
import { queryKeys } from '@/services/query-keys';


export interface MailConfig {
  mail_server: string;
  mail_port: number;
  mail_use_tls: boolean;
  mail_use_ssl: boolean;
  mail_username: string;
  mail_password: string;       
  mail_password_set: boolean;  
  mail_default_sender: string;
  mail_timeout: number;
}

export type MailConfigUpdate = Partial<{
  mail_server: string;
  mail_port: number;
  mail_use_tls: boolean;
  mail_use_ssl: boolean;
  mail_username: string;
  mail_password: string;
  mail_default_sender: string;
  mail_timeout: number;
}>;

export interface MailTestResult {
  success: boolean;
  message: string;
}


async function fetchMailConfig(): Promise<MailConfig> {
  const res = await get<MailConfig>('/settings/mail');
  return res.data;
}

async function updateMailConfig(data: MailConfigUpdate): Promise<MailConfig> {
  const res = await put<MailConfig>('/settings/mail', data);
  return res.data;
}

async function deleteMailConfig(): Promise<void> {
  await del('/settings/mail');
}

export interface MailTestParams {
  recipient: string;
}

async function testMailConfig(data: MailTestParams): Promise<MailTestResult> {
  const res = await post<MailTestResult>('/settings/mail/test', data);
  
  return { success: res.success, message: res.message };
}


export function useMailConfig() {
  return useQuery({
    queryKey: queryKeys.mailSettings.config,
    queryFn: fetchMailConfig,
  });
}

export function useUpdateMailConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updateMailConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mailSettings.all });
    },
  });
}

export function useDeleteMailConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteMailConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mailSettings.all });
    },
  });
}

export function useTestMailConfig() {
  return useMutation({
    mutationFn: testMailConfig,
  });
}
