/**
 * 通知服务
 *
 * 未读数刷新已从 15s 轮询改为 SSE 事件驱动：
 * 后端 notification_service.notify() 创建通知后自动推送 notification_created 事件，
 * 前端 useGlobalEvents 收到后 invalidateQueries 驱动刷新。
 * refetchInterval 仅作为 SSE 不可用时的兜底（60s 间隔，远低于原 15s）。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';


export interface NotificationItem {
  id: number;
  receipt_id: number;
  type: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  content: string | null;
  payload: Record<string, unknown> | null;
  source_module: string | null;
  is_read: boolean;
  read_at: string | null;
  ack_required: boolean;
  acked_at: string | null;
  created_at: string;
}

export interface NotificationListResult {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface NotificationListParams {
  page?: number;
  per_page?: number;
  unread_only?: boolean;
}


async function fetchUnreadCount(): Promise<number> {
  const res = await get<{ unread_count: number }>('/notifications/unread-count');
  return res.data?.unread_count ?? 0;
}

async function fetchNotifications(
  params?: NotificationListParams
): Promise<NotificationListResult> {
  const res = await get<NotificationListResult>(
    '/notifications',
    params as Record<string, unknown>
  );
  return res.data ?? { items: [], total: 0, unread_count: 0 };
}

async function markRead(notificationIds?: number[] | null): Promise<number> {
  const res = await post<{ marked_count: number }, { notification_ids?: number[] | null }>(
    '/notifications/mark-read',
    { notification_ids: notificationIds ?? null }
  );
  return res.data?.marked_count ?? 0;
}

async function ackNotification(notificationId: number): Promise<void> {
  await post(`/notifications/${notificationId}/ack`, {});
}

async function deleteReadNotifications(): Promise<number> {
  const res = await del<{ deleted_count: number }>('/notifications/read');
  return res.data?.deleted_count ?? 0;
}


export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: fetchUnreadCount,
    refetchInterval: 60_000, 
    enabled
  });
}


export function useNotificationList(params?: NotificationListParams, enabled = true) {
  return useQuery({
    queryKey: queryKeys.notifications.list(params),
    queryFn: () => fetchNotifications(params),
    enabled
  });
}


export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationIds?: number[] | null) => markRead(notificationIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    }
  });
}


export function useAckNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) => ackNotification(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    }
  });
}


export function useDeleteReadNotifications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteReadNotifications,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    }
  });
}


export interface NotificationPrefs {
  channels: {
    inbox: boolean;
    email: boolean;
  };
  subscribed_types: string[];
  quiet_hours: {
    enabled: boolean;
    start: string;
    end: string;
  };
}

async function fetchNotificationPreferences(): Promise<NotificationPrefs> {
  const res = await get<NotificationPrefs>('/notifications/preferences');
  return (
    res.data ?? {
      channels: { inbox: true, email: true },
      subscribed_types: [],
      quiet_hours: { enabled: false, start: '22:00', end: '08:00' }
    }
  );
}

async function updateNotificationPreferences(
  prefs: Partial<NotificationPrefs>
): Promise<NotificationPrefs> {
  const res = await put<NotificationPrefs, Partial<NotificationPrefs>>(
    '/notifications/preferences',
    prefs
  );
  return res.data;
}


export function useNotificationPreferences(enabled = true) {
  return useQuery({
    queryKey: queryKeys.notifications.preferences,
    queryFn: fetchNotificationPreferences,
    enabled
  });
}


export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prefs: Partial<NotificationPrefs>) => updateNotificationPreferences(prefs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.preferences });
    }
  });
}


export type BroadcastChannel = 'wechat_work' | 'feishu' | 'custom';

export interface WebhookConfig {
  id: number;
  name: string;
  channel: BroadcastChannel;
  url: string;
  secret: string | null;
  enabled: boolean;
  message_template: Record<string, unknown> | null;
  applicable_types: string[] | null;
  applicable_severities: string[] | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWebhookConfigParams {
  name: string;
  channel: BroadcastChannel;
  url: string;
  secret?: string;
  enabled?: boolean;
  message_template?: Record<string, unknown> | null;
  applicable_types?: string[] | null;
  applicable_severities?: string[] | null;
}

export interface TestWebhookResult {
  success: boolean;
  message: string;
  response_code?: number;
}

async function fetchWebhookConfigs(): Promise<WebhookConfig[]> {
  const res = await get<WebhookConfig[]>('/webhook-configs');
  return res.data ?? [];
}

async function createWebhookConfig(data: CreateWebhookConfigParams): Promise<WebhookConfig> {
  const res = await post<WebhookConfig, CreateWebhookConfigParams>('/webhook-configs', data);
  return res.data;
}

async function updateWebhookConfig(
  id: number,
  data: Partial<CreateWebhookConfigParams>
): Promise<WebhookConfig> {
  const res = await put<WebhookConfig, Partial<CreateWebhookConfigParams>>(
    `/webhook-configs/${id}`,
    data
  );
  return res.data;
}

async function deleteWebhookConfig(id: number): Promise<void> {
  await del(`/webhook-configs/${id}`);
}

async function testWebhookConfig(id: number): Promise<TestWebhookResult> {
  const res = await post<TestWebhookResult>(`/webhook-configs/${id}/test`, {});
  return res.data ?? { success: false, message: '测试失败' };
}


export function useWebhookConfigs(enabled = true) {
  return useQuery({
    queryKey: queryKeys.webhookConfigs.list,
    queryFn: fetchWebhookConfigs,
    enabled
  });
}


export function useCreateWebhookConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateWebhookConfigParams) => createWebhookConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.webhookConfigs.all });
    }
  });
}


export function useUpdateWebhookConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<CreateWebhookConfigParams> }) =>
      updateWebhookConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.webhookConfigs.all });
    }
  });
}


export function useDeleteWebhookConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWebhookConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.webhookConfigs.all });
    }
  });
}


export function useTestWebhookConfig() {
  return useMutation({
    mutationFn: (id: number) => testWebhookConfig(id)
  });
}
