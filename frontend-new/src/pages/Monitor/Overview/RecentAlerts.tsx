/**
 * 监控总览 - 最近告警事件表
 *
 * 重构（M29）：增加行内快捷确认/关闭按钮，无需跳转告警中心即可处理。
 * - severity 用左侧色条（4px）直观标识
 * - pending/sent 状态显示操作按钮，已确认/已关闭隐藏
 * - 操作后乐观更新，失败回滚
 */
import { Card, Empty, Tag, Button, Typography, Space, Tooltip, theme } from 'antd';
import DataTable from '@/components/DataTable';
import { Link } from 'react-router-dom';
import { CheckOutlined, CloseOutlined, RightOutlined } from '@ant-design/icons';
import {
  useMonitorAlerts,
  useAckAlert,
  useCloseAlert,
  type MonitorAlertItem
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { relativeTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { ALERT_TYPE_COLOR } from '@/constants/monitor';
import { NOTIFICATION_TYPE_LABEL_KEYS, type NotificationTypeCode } from '@/types';
import AlertInterpret from './AlertInterpret';

const alertTypeLabel = (type: string, td: TFunction<'device'>) => {
  const key = NOTIFICATION_TYPE_LABEL_KEYS[type as NotificationTypeCode];
  return key ? td(key) : type;
};

const { Text } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  critical: 'red'
};

const SEVERITY_BAR: Record<string, string> = {
  critical: '#ff4d4f',
  warning: '#faad14',
  info: '#1890ff'
};

interface RecentAlertsProps {
  loading: boolean;
}

export default function RecentAlerts({ loading }: RecentAlertsProps) {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const { token } = theme.useToken();
  const message = useMessage();
  const { data: recentAlerts } = useMonitorAlerts({ per_page: 8 });
  const ackAlert = useAckAlert();
  const closeAlert = useCloseAlert();

  const handleAck = async (id: number) => {
    try {
      await ackAlert.mutateAsync({ alertId: id });
      message.success(t('alerts.acknowledged'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.ackFailed'));
    }
  };

  const handleClose = async (id: number) => {
    try {
      await closeAlert.mutateAsync({ alertId: id });
      message.success(t('alerts.message.closed'));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('alerts.message.closeFailed'));
    }
  };

  const items = recentAlerts?.items ?? [];

  return (
    <Card
      title={t('recent.title')}
      loading={loading}
      extra={
        <Link to="/monitor/alerts">
          <Button type="link" size="small" icon={<RightOutlined />}>
            {t('recent.viewAll')}
          </Button>
        </Link>
      }
    >
      {items.length > 0 ? (
        <DataTable<MonitorAlertItem>
          searchable={false}
          showCard={false}
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={items}
          rowClassName={(r) => (r.severity === 'critical' ? 'alert-row-critical' : '')}
          columns={[
            {
              title: t('column.device'),
              key: 'device',
              render: (_: unknown, r: MonitorAlertItem) =>
                r.device_id ? (
                  <Link to={`/devices/${r.device_id}`}>{r.device_name || `#${r.device_id}`}</Link>
                ) : (
                  '—'
                )
            },
            {
              title: t('column.alertType'),
              key: 'alert_type',
              width: 140,
              render: (_: unknown, r: MonitorAlertItem) => (
                <Tag color={ALERT_TYPE_COLOR[r.alert_type] || 'default'}>
                  {alertTypeLabel(r.alert_type, td)}
                </Tag>
              )
            },
            {
              title: tc('field.level'),
              key: 'severity',
              width: 90,
              render: (_: unknown, r: MonitorAlertItem) => (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 4,
                      height: 14,
                      borderRadius: 2,
                      background: SEVERITY_BAR[r.severity ?? ''] ?? token.colorBorder
                    }}
                  />
                  <Tag color={SEVERITY_COLOR[r.severity ?? ''] || 'default'}>{r.severity}</Tag>
                </span>
              )
            },
            {
              title: t('column.content'),
              key: 'content',
              ellipsis: true,
              render: (_: unknown, r: MonitorAlertItem) => {
                try {
                  const parsed = r.payload_json ? JSON.parse(r.payload_json) : null;
                  return parsed?.title || r.alert_type;
                } catch {
                  return r.alert_type;
                }
              }
            },
            {
              title: tc('field.time'),
              dataIndex: 'created_at',
              key: 'created_at',
              width: 120,
              render: (v: string | null) => relativeTime(v, tc)
            },
            {
              title: tc('field.actions'),
              key: 'action',
              width: 120,
              render: (_: unknown, r: MonitorAlertItem) => {
                const isPending = r.status === 'pending' || r.status === 'sent';
                return (
                  <Space size={4} direction="vertical" align="start">
                    <Space size={4}>
                      {isPending ? (
                        <>
                          <Tooltip title={tc('action.confirm')}>
                            <Button
                              type="text"
                              size="small"
                              icon={<CheckOutlined />}
                              loading={ackAlert.isPending}
                              onClick={() => handleAck(r.id)}
                              style={{ color: token.colorSuccess }}
                            />
                          </Tooltip>
                          <Tooltip title={tc('action.close')}>
                            <Button
                              type="text"
                              size="small"
                              icon={<CloseOutlined />}
                              loading={closeAlert.isPending}
                              onClick={() => handleClose(r.id)}
                              style={{ color: token.colorError }}
                            />
                          </Tooltip>
                        </>
                      ) : (
                        <Text type="secondary">{t('recent.handled')}</Text>
                      )}
                    </Space>
                    <AlertInterpret
                      alert={{
                        alert_type: r.alert_type,
                        device_name: r.device_name ?? undefined,
                        severity: r.severity ?? undefined
                      }}
                    />
                  </Space>
                );
              }
            }
          ]}
        />
      ) : (
        <Empty description={t('recent.empty')} />
      )}
    </Card>
  );
}
