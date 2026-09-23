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
import { getNotificationTypeGroupOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

const DEFAULT_QUIET_HOURS = { enabled: false, start: '22:00', end: '08:00' };

const NotificationPreferences: React.FC = () => {
  const { t: tDevice } = useTranslation('device');
  const { t } = useTranslation('settings');
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
        messageApi.success(t('notification.preferences.message.saved'));
      } catch {
        messageApi.error(t('saveFailed'));
      }
    },
    [updateMutation, prefs, messageApi, t]
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
            <span>{t('notification.preferences.title')}</span>
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
            {t('notification.preferences.sectionChannels')}
          </Title>

          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>
              {t('notification.preferences.inbox')}
            </div>
            <Text type="secondary">{t('notification.preferences.inboxHint')}</Text>
          </div>

          <Form.Item label={t('notification.preferences.email')} name="emailEnabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            <MailOutlined style={{ marginRight: 4 }} />
            {t('notification.preferences.emailHint')}
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
                  <Form.Item
                    label={t('notification.preferences.voice')}
                    name="voiceEnabled"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Text
                    type="secondary"
                    style={{ marginTop: -8, marginBottom: 16, display: 'block' }}
                  >
                    <PhoneOutlined style={{ marginRight: 4 }} />
                    {t('notification.preferences.voiceHint')}
                  </Text>
                  {quietOn && voiceOn && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                      message={t('notification.preferences.voiceQuietHoursAlert')}
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
            {t('notification.preferences.sectionTypes')}
          </Title>

          <Form.Item name="subscribedTypes">
            <Select
              mode="multiple"
              placeholder={t('notification.preferences.typesPlaceholder')}
              options={getNotificationTypeGroupOptions(tDevice)}
              style={{ width: '100%' }}
              allowClear
            />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            {t('notification.preferences.typesHint')}
          </Text>

          <Divider />

          {/* ── 免打扰时段 ─────────────────────────────────────── */}
          <Title level={5} style={{ marginBottom: 16 }}>
            <MoonOutlined style={{ marginRight: 8 }} />
            {t('notification.preferences.sectionQuietHours')}
          </Title>

          <Form.Item
            label={t('notification.preferences.quietHoursSwitch')}
            name="quietHoursEnabled"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ marginTop: -8, marginBottom: 16, display: 'block' }}>
            {t('notification.preferences.quietHoursHint')}
          </Text>

          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.quietHoursEnabled !== cur.quietHoursEnabled}
          >
            {({ getFieldValue }) =>
              getFieldValue('quietHoursEnabled') ? (
                <Form.Item
                  label={t('notification.preferences.quietHours')}
                  name="quietHoursRange"
                >
                  <TimePicker.RangePicker
                    format="HH:mm"
                    style={{ width: '100%' }}
                    placeholder={[
                      t('notification.preferences.timeRangePlaceholderStart'),
                      t('notification.preferences.timeRangePlaceholderEnd')
                    ]}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>

          <Divider />

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
              {t('notification.preferences.action.save')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default NotificationPreferences;
