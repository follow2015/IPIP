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

type ConfigValue = number | string | boolean;


const CONFIG_GROUPS: { key: string; title: string; fields: string[] }[] = [
  {
    key: 'probe',
    title: '探测参数',
    fields: ['consecutive_failures_threshold', 'timeout_seconds', 'thread_pool_size']
  },
  {
    key: 'interval',
    title: '轮询间隔',
    fields: ['interval_snmp', 'interval_bmc', 'interval_zabbix', 'outbox_interval']
  },
  {
    key: 'alert',
    title: '告警规则',
    fields: ['realert_interval_minutes', 'fallback_role', 'blindspot_role']
  },
  { key: 'advanced', title: '高级', fields: ['worker_in_process'] },
  {
    key: 'scan',
    title: '自动扫描',
    fields: [
      'scan_auto_enabled',
      'scan_auto_interval',
      'scan_auto_room_ids',
      'scan_auto_vr_ids',
      'scan_auto_cleanup_interval',
      'scan_auto_grace_period'
    ]
  }
];


const FIELD_LABELS: Record<string, string> = {
  consecutive_failures_threshold: '连续失败阈值',
  timeout_seconds: '探测超时(秒)',
  thread_pool_size: '线程池大小',
  interval_snmp: 'SNMP 轮询间隔(秒)',
  interval_bmc: 'BMC 轮询间隔(秒)',
  interval_zabbix: 'Zabbix 轮询间隔(秒)',
  outbox_interval: '告警发件箱间隔(秒)',
  realert_interval_minutes: '重告警间隔(分钟)',
  fallback_role: '兜底角色',
  blindspot_role: '盲区应急组',
  worker_in_process: '进程内 Worker',
  scan_auto_enabled: '自动扫描总开关',
  scan_auto_interval: '扫描间隔(秒)',
  scan_auto_room_ids: '物理机房范围',
  scan_auto_vr_ids: '虚拟机房范围',
  scan_auto_cleanup_interval: '陈旧度清理间隔(秒)',
  scan_auto_grace_period: 'INACTIVE降级宽限期(秒)'
};


export default function MonitorSettings() {
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
    return <Alert type="warning" message="无法加载监控运行配置" />;
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
        `已保存 ${res.updated.length} 项配置，Worker 将热重载${res.requires_restart.length ? '（部分需重启）' : ''}`
      );
    } catch (e) {
      message.error((e as Error)?.message || '保存失败');
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
        <Descriptions.Item key={key} label={FIELD_LABELS[key] ?? key}>
          <Space>
            {item.type === 'bool' ? (
              <Tag color={item.value ? 'green' : 'default'}>{item.value ? '已启用' : '已禁用'}</Tag>
            ) : (
              <span>{String(item.value)}</span>
            )}
            <Tag color="default">需重启</Tag>
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
          placeholder="选择机房（留空则不启用自动扫描）"
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
      <Descriptions.Item key={key} label={FIELD_LABELS[key] ?? key}>
        <Space orientation="vertical" size={2} style={{ width: '100%' }}>
          <Space>
            {control}
            {isDirty && <Tag color="orange">未保存</Tag>}
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

  const tabItems = CONFIG_GROUPS.map((g) => ({
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
      <Alert
        type="info"
        showIcon
        message="可在线修改的参数保存后立即对 Worker 生效（热重载），无需重启；标「需重启」的参数需重启服务。"
      />

      <Tabs items={tabItems} />

      <div>
        <Space>
          <Button
            type="primary"
            onClick={handleSave}
            disabled={dirty.size === 0 || updateConfig.isPending}
            loading={updateConfig.isPending}
          >
            保存修改{dirty.size > 0 ? ` (${dirty.size})` : ''}
          </Button>
          {dirty.size > 0 && <Button onClick={handleReset}>重置</Button>}
        </Space>
      </div>
    </div>
  );
}
