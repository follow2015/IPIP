import React, { useCallback } from 'react';
import {
  Form,
  Switch,
  TimePicker,
  Card,
  Space,
  Button,
  Typography,
  Divider,
  message,
  Spin,
  Select,
  Alert
} from 'antd';
import {
  BellOutlined,
  MailOutlined,
  MoonOutlined,
  FilterOutlined,
  PhoneOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
  type NotificationPrefs
} from '@/services/notification';
import { NOTIFICATION_TYPE_GROUP_OPTIONS } from '@/types/enums';

const { Title, Text } = Typography;

const DEFAULT_QUIET_HOURS = { enabled: false, start: '22:00', end: '08:00' };

const NotificationPreferences: React.FC = () => {
  const { data: prefs, isLoading } = useNotificationPreferences();
  const updateMutation = useUpdateNotificationPreferences();
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const handleSave = useCallback(
    async (values: {
      emailEnabled: boolean;
      voiceEnabled: boolean;
      subscribedTypes: string[];
      quietHoursEnabled: boolean;
      quietHoursRange?: [dayjs.Dayjs, dayjs.Dayjs];
    }) => {
      const quietHours = prefs?.quiet_hours ?? DEFAULT_QUIET_HOURS;
      const update: Partial<NotificationPrefs> = {
        channels: {
          inbox: true,
          email: values.emailEnabled,
          voice: values.voiceEnabled
        },
        subscribed_types: values.subscribedTypes
      };

      if (values.quietHoursEnabled && values.quietHoursRange) {
        update.quiet_hours = {
          enabled: true,
          start: values.quietHoursRange[0].format('HH:mm'),
          end: values.quietHoursRange[1].format('HH:mm')
        };
      } else if (values.quietHoursEnabled) {
        update.quiet_hours = { enabled: true, start: quietHours.start, end: quietHours.end };
      } else {
        update.quiet_hours = { enabled: false, start: quietHours.start, end: quietHours.end };
      }

      try {
        await updateMutation.mutateAsync(update);
        messageApi.success('通知偏好已保存');
      } catch {
        messageApi.error('保存失败，请重试');
      }
    },
    [updateMutation, prefs, messageApi]
  );

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    );
  }

  const quietHours = prefs?.quiet_hours ?? DEFAULT_QUIET_HOURS;
  const quietHoursEnabled = quietHours.enabled;

  return (
    <>
      {contextHolder}
      <Card
        title={
          <Space>
            <BellOutlined />
            <span>通知偏好设置</span>
          </Space>
        }
        style={{ maxWidth: 640 }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{
            emailEnabled: prefs?.channels?.email ?? true,
            voiceEnabled: prefs?.channels?.voice ?? false,
            subscribedTypes: prefs?.subscribed_types ?? [],
            quietHoursEnabled,
            quietHoursRange: [dayjs(quietHours.start, 'HH:mm'), dayjs(quietHours.end, 'HH:mm')]
          }}
        >
          {/* ── 渠道开关 ─────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            投递渠道
          </Title>

          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>站内信</div>
            <Text type="secondary">站内信通知默认开启，无法调整</Text>
          </div>

          <Form.Item label="邮件通知" name="emailEnabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            <MailOutlined style={{ marginRight: 4 }} />
            接收邮件推送（需在个人资料中设置邮箱地址）
          </Text>

          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) =>
              prev.quietHoursEnabled !== cur.quietHoursEnabled ||
              prev.voiceEnabled !== cur.voiceEnabled
            }
          >
            {({ getFieldValue }) => {
              const quietOn = getFieldValue('quietHoursEnabled');
              const voiceOn = getFieldValue('voiceEnabled');
              return (
                <>
                  <Form.Item label="语音通知" name="voiceEnabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Text
                    type="secondary"
                    style={{ marginTop: -8, marginBottom: 16, display: 'block' }}
                  >
                    <PhoneOutlined style={{ marginRight: 4 }} />
                    语音电话呼叫（需管理员启用语音渠道，并在个人资料中设置手机号； 默认关闭）
                  </Text>
                  {quietOn && voiceOn && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                      message="免打扰时段内，语音通知仍会呼出（深夜告警叫醒场景）。若不希望夜间接到电话，请关闭语音通知。"
                    />
                  )}
                </>
              );
            }}
          </Form.Item>

          <Divider />

          {/* ── 订阅类型 ─────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            <FilterOutlined style={{ marginRight: 8 }} />
            订阅类型
          </Title>

          <Form.Item name="subscribedTypes">
            <Select
              mode="multiple"
              placeholder="不选择则接收全部类型通知"
              options={NOTIFICATION_TYPE_GROUP_OPTIONS}
              style={{ width: '100%' }}
              allowClear
            />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            选择要接收的通知类别。不选择则接收全部类型；严重（critical）级别通知始终穿透，不受此过滤影响。
          </Text>

          <Divider />

          {/* ── 免打扰时段 ─────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            <MoonOutlined style={{ marginRight: 8 }} />
            免打扰时段
          </Title>

          <Form.Item label="启用免打扰" name="quietHoursEnabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            开启后，在设定时段内仅接收严重（critical）级别通知
          </Text>

          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.quietHoursEnabled !== cur.quietHoursEnabled}
          >
            {({ getFieldValue }) =>
              getFieldValue('quietHoursEnabled') ? (
                <Form.Item label="免打扰时段" name="quietHoursRange">
                  <TimePicker.RangePicker
                    format="HH:mm"
                    style={{ width: '100%' }}
                    placeholder={['开始时间', '结束时间']}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>

          <Divider />

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
              保存偏好
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default NotificationPreferences;
