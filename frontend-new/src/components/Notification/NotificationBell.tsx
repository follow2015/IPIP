/**
 * NotificationBell — 通知铃铛 + 未读红点 + 下拉面板
 *
 * 集成到 Header 右侧，使用 Ant Design Badge + Popover + List。
 * 未读数通过 TanStack Query 15s 轮询刷新，不使用 SSE 长连接。
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  Badge,
  Popover,
  List,
  Button,
  Empty,
  Space,
  Tag,
  Typography,
  theme,
  Popconfirm
} from 'antd';
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
import { SEVERITY_COLOR_MAP, SEVERITY_LABELS } from '@/types/enums';

const { Text, Paragraph } = Typography;


function NotificationItemRow({
  item,
  onRead
}: {
  item: NotificationItem;
  onRead: (id: number) => void;
}) {
  const { token } = theme.useToken();
  
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
              {SEVERITY_LABELS[item.severity] ?? item.severity}
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
                symbol: (expandedState) => (expandedState ? '收起' : '展开'),
                onExpand: (_e, info) => setExpanded(info.expanded)
              }}
              style={{ marginBottom: 0, fontSize: 12 }}
            >
              {item.content}
            </Paragraph>
          ) : null
        }
      />
      <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
        {formatTime(item.created_at)}
      </Text>
    </List.Item>
  );
}


function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay}天前`;
  return d.toLocaleDateString('zh-CN');
}


function NotificationBell() {
  const { token } = theme.useToken();
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
      
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
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
    markReadMutation.mutate(null); 
  }, [markReadMutation]);

  const handleClearRead = useCallback(() => {
    deleteReadMutation.mutate();
  }, [deleteReadMutation]);

  
  useGlobalEventListener((event) => {
    if (event.event_type !== 'monitor_alert') return;
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    const payload = event.payload as Record<string, unknown>;
    const severity = String(payload.severity ?? 'warning');
    const alertType = String(payload.alert_type ?? '告警');
    const title = `[${SEVERITY_LABELS[severity] ?? severity}] 监控告警`;
    const body = `${alertType}（设备 #${payload.device_id ?? '-'}）`;
    try {
      new Notification(title, { body, tag: String(payload.dedup_key ?? '') });
    } catch {
      
    }
  });

  
  const content = (
    <div style={{ width: 380, maxHeight: 480, overflow: 'auto' }}>
      {}
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
          消息通知
        </Text>
        <Space size={4}>
          {hasReadItems && (
            <Popconfirm
              title="确认清除所有已读消息？"
              description="未读消息将保留"
              onConfirm={handleClearRead}
              okText="清除"
              cancelText="取消"
              okButtonProps={{ danger: true, size: 'small' }}
            >
              <Button
                type="link"
                size="small"
                icon={<ClearOutlined />}
                style={{ padding: 0, fontSize: 12 }}
              >
                清除已读
              </Button>
            </Popconfirm>
          )}
          {unreadCount > 0 && (
            <Button
              type="link"
              size="small"
              icon={<CheckOutlined />}
              onClick={handleMarkAllRead}
              style={{ padding: 0, fontSize: 12 }}
            >
              全部已读
            </Button>
          )}
        </Space>
      </div>

      {}
      {isLoading ? (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <Text type="secondary">加载中...</Text>
        </div>
      ) : !sortedItems.length ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无通知"
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
