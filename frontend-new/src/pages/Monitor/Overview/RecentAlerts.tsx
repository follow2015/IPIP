/**
 * 监控总览 - 最近告警事件表
 *
 * 重构（M29）：增加行内快捷确认/关闭按钮，无需跳转告警中心即可处理。
 * - severity 用左侧色条（4px）直观标识
 * - pending/sent 状态显示操作按钮，已确认/已关闭隐藏
 * - 操作后乐观更新，失败回滚
 */
import { Card, Empty, Table, Tag, Button, Typography, Space, Tooltip, theme } from 'antd';
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
import { ALERT_TYPE_LABEL, ALERT_TYPE_COLOR } from '@/constants/monitor';

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
  const { token } = theme.useToken();
  const message = useMessage();
  const { data: recentAlerts } = useMonitorAlerts({ per_page: 8 });
  const ackAlert = useAckAlert();
  const closeAlert = useCloseAlert();

  const handleAck = async (id: number) => {
    try {
      await ackAlert.mutateAsync({ alertId: id });
      message.success('已确认');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '确认失败');
    }
  };

  const handleClose = async (id: number) => {
    try {
      await closeAlert.mutateAsync({ alertId: id });
      message.success('已关闭');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '关闭失败');
    }
  };

  const items = recentAlerts?.items ?? [];

  return (
    <Card
      title="最近告警"
      loading={loading}
      extra={
        <Link to="/monitor/alerts">
          <Button type="link" size="small" icon={<RightOutlined />}>
            查看全部
          </Button>
        </Link>
      }
    >
      {items.length > 0 ? (
        <Table<MonitorAlertItem>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={items}
          rowClassName={(r) => (r.severity === 'critical' ? 'alert-row-critical' : '')}
          columns={[
            {
              title: '设备',
              key: 'device',
              render: (_: unknown, r: MonitorAlertItem) =>
                r.device_id ? (
                  <Link to={`/devices/${r.device_id}`}>{r.device_name || `#${r.device_id}`}</Link>
                ) : (
                  '—'
                )
            },
            {
              title: '告警类型',
              key: 'alert_type',
              width: 140,
              render: (_: unknown, r: MonitorAlertItem) => (
                <Tag color={ALERT_TYPE_COLOR[r.alert_type] || 'default'}>
                  {ALERT_TYPE_LABEL[r.alert_type] || r.alert_type}
                </Tag>
              )
            },
            {
              title: '级别',
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
              title: '内容',
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
              title: '时间',
              dataIndex: 'created_at',
              key: 'created_at',
              width: 120,
              render: relativeTime
            },
            {
              title: '操作',
              key: 'action',
              width: 80,
              render: (_: unknown, r: MonitorAlertItem) => {
                const isPending = r.status === 'pending' || r.status === 'sent';
                if (!isPending) return <Text type="secondary">已处理</Text>;
                return (
                  <Space size={4}>
                    <Tooltip title="确认">
                      <Button
                        type="text"
                        size="small"
                        icon={<CheckOutlined />}
                        loading={ackAlert.isPending}
                        onClick={() => handleAck(r.id)}
                        style={{ color: token.colorSuccess }}
                      />
                    </Tooltip>
                    <Tooltip title="关闭">
                      <Button
                        type="text"
                        size="small"
                        icon={<CloseOutlined />}
                        loading={closeAlert.isPending}
                        onClick={() => handleClose(r.id)}
                        style={{ color: token.colorError }}
                      />
                    </Tooltip>
                  </Space>
                );
              }
            }
          ]}
        />
      ) : (
        <Empty description="暂无最近告警" />
      )}
    </Card>
  );
}
