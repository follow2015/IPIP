/**
 * NotificationBell — 通知铃铛 + 未读红点 + 下拉面板
 *
 * 集成到 Header 右侧，使用 Ant Design Badge + Popover + List。
 * 未读数通过 TanStack Query 15s 轮询刷新，不使用 SSE 长连接。
 */
import React, { useCallback, useMemo, useState } from 'react';
import { Badge, Popover, List, Button, Empty, Space, Tag, Typography, theme } from 'antd';
import { useConfirm } from '@/utils/confirm';
import { BellOutlined, CheckOutlined, DeleteOutlined, ClearOutlined } from '@ant-design/icons';
import {
  useUnreadCount,
  useNotificationList,
  useMarkRead,
  useDeleteReadNotifications,
  type NotificationItem
} from '@/services/notification';
import { useAuthStore } from '@/stores/auth';
import { useGlobalEventListener } from '@/hooks/useGlobalEvents';
import { SEVERITY_COLOR_MAP } from '@/types/enums';
import { getSeverityLabel } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { formatDate, parseServerTime } from '@/utils/format';

const { Text, Paragraph } = Typography;

type NotificationT = TFunction<'settings'>;

function NotificationItemRow({
  item,
  onRead
}: {
  item: NotificationItem;
  onRead: (id: number) => void;
}) {
  const { token } = theme.useToken();
  const { t: tDevice } = useTranslation('device');
  const { t } = useTranslation('settings');
  const [expanded, setExpanded] = useState(false);

  return (
    <List.Item
      style={{
        padding: '12px 16px',
        cursor: 'pointer',
        background: item.is_read ? 'transparent' : token.colorPrimaryBg,
        transition: 'background 0.2s'
      }}
      onClick={() => {
        if (!item.is_read) onRead(item.id);
      }}
    >
      <List.Item.Meta
        title={
          <Space size={4}>
            <Tag color={SEVERITY_COLOR_MAP[item.severity]} style={{ marginRight: 0 }}>
              {getSeverityLabel(item.severity, tDevice) ?? item.severity}
            </Tag>
            <Text strong={!item.is_read} style={{ fontSize: 13 }}>
              {item.title}
            </Text>
          </Space>
        }
        description={
          item.content ? (
            <Paragraph
              type="secondary"
              ellipsis={{
                rows: 2,
                expandable: true,
                expanded,
                symbol: (expandedState) =>
                  expandedState ? t('notification.bell.collapse') : t('notification.bell.expand'),
                onExpand: (_e, info) => setExpanded(info.expanded)
              }}
              style={{ marginBottom: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}
            >
              {item.content}
            </Paragraph>
          ) : null
        }
      />
      <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
        {formatTime(item.created_at, t)}
      </Text>
    </List.Item>
  );
}

function formatTime(iso: string | null, t: NotificationT): string {
  if (!iso) return '';
  const d = parseServerTime(iso);
  if (!d) return '';
  const diffMs = Date.now() - d.valueOf();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return t('notification.bell.time.justNow');
  if (diffMin < 60) return t('notification.bell.time.minutesAgo', { count: diffMin });
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return t('notification.bell.time.hoursAgo', { count: diffHour });
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return t('notification.bell.time.daysAgo', { count: diffDay });
  return formatDate(iso);
}

function NotificationBell() {
  const confirm = useConfirm();
  const { token } = theme.useToken();
  const { t: tDevice } = useTranslation('device');
  const { t } = useTranslation('settings');
  const { t: tCommon } = useTranslation('common');
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [open, setOpen] = useState(false);

  const { data: unreadCount = 0 } = useUnreadCount(isAuthenticated);

  const { data: listResult, isLoading } = useNotificationList({ per_page: 20 }, open);

  const markReadMutation = useMarkRead();

  const deleteReadMutation = useDeleteReadNotifications();

  const sortedItems = useMemo(() => {
    const items = listResult?.items ?? [];
    return [...items].sort((a, b) => {
      if (a.is_read !== b.is_read) return a.is_read ? 1 : -1;
      return (
        (parseServerTime(b.created_at)?.valueOf() ?? 0) -
        (parseServerTime(a.created_at)?.valueOf() ?? 0)
      );
    });
  }, [listResult?.items]);

  const hasReadItems = sortedItems.some((item) => item.is_read);

  const handleRead = useCallback(
    (notificationId: number) => {
      markReadMutation.mutate([notificationId]);
    },
    [markReadMutation]
  );

  const handleMarkAllRead = useCallback(() => {
    markReadMutation.mutate(null); // null = 全部标记已读
  }, [markReadMutation]);

  const handleClearRead = useCallback(() => {
    deleteReadMutation.mutate();
  }, [deleteReadMutation]);

  useGlobalEventListener((event) => {
    if (event.event_type !== 'monitor_alert') return;
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    const payload = event.payload as Record<string, unknown>;
    const severity = String(payload.severity ?? 'warning');
    const alertType = String(
      payload.alert_type ?? t('notification.bell.browserNotification.defaultAlertType')
    );
    const title = t('notification.bell.browserNotification.title', {
      severity: getSeverityLabel(severity, tDevice) ?? severity
    });
    const body = t('notification.bell.browserNotification.body', {
      alertType,
      deviceId: String(payload.device_id ?? '-')
    });
    try {
      new Notification(title, { body, tag: String(payload.dedup_key ?? '') });
    } catch {
    }
  });

  const content = (
    <div style={{ width: 380, maxHeight: 480, overflow: 'auto' }}>
      {/* 顶部操作栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 16px',
          borderBottom: `1px solid ${token.colorBorderSecondary}`
        }}
      >
        <Text strong style={{ fontSize: 14 }}>
          {t('notification.bell.title')}
        </Text>
        <Space size={4}>
          {hasReadItems && (
            <Button
              type="link"
              size="small"
              icon={<ClearOutlined />}
              style={{ padding: 0, fontSize: 12 }}
              onClick={() =>
                confirm({
                  title: t('notification.bell.deleteReadConfirmTitle'),
                  content: t('notification.bell.deleteReadConfirmContent'),
                  okText: t('notification.bell.clearRead'),
                  cancelText: tCommon('action.cancel'),
                  okButtonProps: { danger: true, size: 'small' },
                  onOk: handleClearRead
                })
              }
            >
              {t('notification.bell.clearRead')}
            </Button>
          )}
          {unreadCount > 0 && (
            <Button
              type="link"
              size="small"
              icon={<CheckOutlined />}
              onClick={handleMarkAllRead}
              style={{ padding: 0, fontSize: 12 }}
            >
              {t('notification.bell.markAllRead')}
            </Button>
          )}
        </Space>
      </div>

      {/* 通知列表 */}
      {isLoading ? (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <Text type="secondary">{tCommon('message.loading')}</Text>
        </div>
      ) : !sortedItems.length ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('notification.bell.empty')}
          style={{ padding: '40px 0' }}
        />
      ) : (
        <List
          dataSource={sortedItems}
          renderItem={(item) => (
            <NotificationItemRow key={item.id} item={item} onRead={handleRead} />
          )}
          style={{ maxHeight: 400, overflow: 'auto' }}
        />
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      placement="bottomRight"
      overlayStyle={{ padding: 0 }}
      open={open}
      onOpenChange={setOpen}
    >
      <Badge count={unreadCount} size="small" offset={[-2, 2]}>
        <Button
          type="text"
          icon={<BellOutlined />}
          style={{ fontSize: 16, color: token.colorText }}
        />
      </Badge>
    </Popover>
  );
}

export default NotificationBell;
