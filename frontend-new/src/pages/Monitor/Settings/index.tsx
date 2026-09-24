/**
 * 监控中心 - 运行配置页（P0-1 / P2-8）
 *
 * 可在线编辑监控运行参数（阈值 / 轮询间隔 / 告警角色 / 线程池）。
 * 配置源自后端动态配置（Redis + DB 双写），保存后经 PUT /config 双写，
 * Worker 每轮从动态配置读取实现热重载，无需重启（标「需重启」者除外）。
 *
 * 布局：Tabs 分组 [探测参数][轮询间隔][告警规则][高级]，与白名单 key 一一对应。
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Tabs,
  Descriptions,
  InputNumber,
  Input,
  Switch,
  Select,
  Tag,
  Skeleton,
  Alert,
  Button,
  Space,
  theme
} from 'antd';
import { useMonitorConfig, useUpdateMonitorConfig } from '@/services/monitor';
import { useRoomOptions } from '@/services/room';
import { useVirtualRooms } from '@/services/virtual-room';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

type ConfigValue = number | string | boolean;

const getConfigGroups = (
  t: TFunction<'monitor'>
): { key: string; title: string; fields: string[] }[] => [
  {
    key: 'probe',
    title: t('settings.group.probe'),
    fields: ['consecutive_failures_threshold', 'timeout_seconds', 'thread_pool_size']
  },
  {
    key: 'interval',
    title: t('settings.group.interval'),
    fields: ['interval_snmp', 'interval_bmc', 'interval_zabbix', 'outbox_interval']
  },
  {
    key: 'alert',
    title: t('settings.group.alert'),
    fields: ['realert_interval_minutes', 'fallback_role', 'blindspot_role']
  },
  { key: 'advanced', title: t('settings.group.advanced'), fields: ['worker_in_process'] },
  {
    key: 'scan',
    title: t('settings.group.scan'),
    fields: [
      'scan_auto_enabled',
      'scan_auto_cleanup_enabled',
      'scan_auto_interval',
      'scan_auto_room_ids',
      'scan_auto_vr_ids',
      'scan_auto_cleanup_interval',
      'scan_auto_grace_period'
    ]
  }
];

const getFieldLabel = (key: string, t: TFunction<'monitor'>) =>
  ({
    consecutive_failures_threshold: t('settings.field.consecutiveFailuresThreshold'),
    timeout_seconds: t('settings.field.timeoutSeconds'),
    thread_pool_size: t('settings.field.threadPoolSize'),
    interval_snmp: t('settings.field.intervalSnmp'),
    interval_bmc: t('settings.field.intervalBmc'),
    interval_zabbix: t('settings.field.intervalZabbix'),
    outbox_interval: t('settings.field.outboxInterval'),
    realert_interval_minutes: t('settings.field.realertIntervalMinutes'),
    fallback_role: t('settings.field.fallbackRole'),
    blindspot_role: t('settings.field.blindspotRole'),
    worker_in_process: t('settings.field.workerInProcess'),
    scan_auto_enabled: t('settings.field.scanAutoEnabled'),
    scan_auto_cleanup_enabled: t('settings.field.scanAutoCleanupEnabled'),
    scan_auto_interval: t('settings.field.scanAutoInterval'),
    scan_auto_room_ids: t('settings.field.scanAutoRoomIds'),
    scan_auto_vr_ids: t('settings.field.scanAutoVrIds'),
    scan_auto_cleanup_interval: t('settings.field.scanAutoCleanupInterval'),
    scan_auto_grace_period: t('settings.field.scanAutoGracePeriod')
  })[key] ?? key;

export default function MonitorSettings() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { data: config, isLoading } = useMonitorConfig();
  const updateConfig = useUpdateMonitorConfig();
  const [values, setValues] = useState<Record<string, ConfigValue>>({});
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const message = useMessage();
  const { token } = theme.useToken();

  const { data: roomOptions } = useRoomOptions();
  const { data: virtualRoomsData } = useVirtualRooms({ per_page: 200 });
  const virtualRoomOptions = useMemo(
    () => (virtualRoomsData?.items ?? []).map((vr) => ({ label: vr.name, value: vr.id })),
    [virtualRoomsData]
  );

  useEffect(() => {
    if (!config) return;
    const init: Record<string, ConfigValue> = {};
    Object.entries(config).forEach(([key, item]) => {
      if (item.editable) init[key] = item.value;
    });
    setValues(init);
    setDirty(new Set());
  }, [config]);

  if (isLoading) {
    return <Skeleton active paragraph={{ rows: 6 }} />;
  }

  if (!config) {
    return <Alert type="warning" message={t('settings.loadFailed')} />;
  }

  const handleChange = (key: string, val: ConfigValue) => {
    const original = config[key]?.value;
    setValues((prev) => ({ ...prev, [key]: val }));
    setDirty((prev) => {
      const next = new Set(prev);
      if (original === val) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSave = async () => {
    if (dirty.size === 0) return;
    const updates: Record<string, ConfigValue> = {};
    dirty.forEach((k) => {
      updates[k] = values[k];
    });
    try {
      const res = await updateConfig.mutateAsync(updates);
      message.success(
        t('settings.message.saved', { count: res.updated.length }) +
          (res.requires_restart.length ? t('settings.message.savedRestartSuffix') : '')
      );
    } catch (e) {
      message.error((e as Error)?.message || t('settings.message.saveFailed'));
    }
  };

  const handleReset = () => {
    const init: Record<string, ConfigValue> = {};
    Object.entries(config).forEach(([key, item]) => {
      if (item.editable) init[key] = item.value;
    });
    setValues(init);
    setDirty(new Set());
  };

  const renderField = (key: string) => {
    const item = config[key];
    if (!item) return null;
    const isDirty = dirty.has(key);

    if (!item.editable) {
      return (
        <Descriptions.Item key={key} label={getFieldLabel(key, t)}>
          <Space>
            {item.type === 'bool' ? (
              <Tag color={item.value ? 'green' : 'default'}>
                {item.value ? t('settings.enabled') : t('settings.disabled')}
              </Tag>
            ) : (
              <span>{String(item.value)}</span>
            )}
            <Tag color="default">{t('settings.needRestart')}</Tag>
          </Space>
        </Descriptions.Item>
      );
    }

    let control;
    if (item.type === 'int' || item.type === 'float') {
      control = (
        <InputNumber
          value={values[key] as number}
          min={1}
          onChange={(v) => v !== null && handleChange(key, v)}
          style={{ width: 180 }}
        />
      );
    } else if (item.type === 'bool') {
      control = <Switch checked={Boolean(values[key])} onChange={(v) => handleChange(key, v)} />;
    } else if (key === 'scan_auto_room_ids' || key === 'scan_auto_vr_ids') {
      const opts = key === 'scan_auto_room_ids' ? (roomOptions ?? []) : virtualRoomOptions;
      const strVal = String(values[key] ?? '');
      const arrVal = strVal
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
        .filter((n) => !Number.isNaN(n));
      control = (
        <Select
          mode="multiple"
          placeholder={t('settings.selectRoomPlaceholder')}
          options={opts}
          value={arrVal}
          onChange={(selected: number[]) => handleChange(key, selected.join(','))}
          style={{ minWidth: 280, maxWidth: 480 }}
          allowClear
          showSearch
          optionFilterProp="label"
        />
      );
    } else {
      control = (
        <Input
          value={String(values[key] ?? '')}
          onChange={(e) => handleChange(key, e.target.value)}
          style={{ width: 240 }}
        />
      );
    }

    return (
      <Descriptions.Item key={key} label={getFieldLabel(key, t)}>
        <Space orientation="vertical" size={2} style={{ width: '100%' }}>
          <Space>
            {control}
            {isDirty && <Tag color="orange">{t('settings.unsaved')}</Tag>}
          </Space>
          {item.description && (
            <span style={{ color: token.colorTextDescription, fontSize: 12 }}>
              {item.description}
            </span>
          )}
        </Space>
      </Descriptions.Item>
    );
  };

  const tabItems = getConfigGroups(t).map((g) => ({
    key: g.key,
    label: g.title,
    children: (
      <Card size="small">
        <Descriptions column={1} bordered size="small">
          {g.fields.map(renderField)}
        </Descriptions>
      </Card>
    )
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert type="info" showIcon message={t('settings.hint')} />

      <Tabs items={tabItems} />

      <div>
        <Space>
          <Button
            type="primary"
            onClick={handleSave}
            disabled={dirty.size === 0 || updateConfig.isPending}
            loading={updateConfig.isPending}
          >
            {`${t('settings.save')}${dirty.size > 0 ? ` (${dirty.size})` : ''}`}
          </Button>
          {dirty.size > 0 && <Button onClick={handleReset}>{tc('action.reset')}</Button>}
        </Space>
      </div>
    </div>
  );
}
