import { Typography } from 'antd';
import type { TFunction } from 'i18next';

const { Text } = Typography;

export type MetricDeviceTypeKey =
  | 'deviceType.NETWORK'
  | 'deviceType.SERVER'
  | 'deviceType.OTHER';

export const DEVICE_TYPE_LABEL_KEYS: Record<string, MetricDeviceTypeKey> = {
  network: 'deviceType.NETWORK',
  server: 'deviceType.SERVER',
  other: 'deviceType.OTHER'
};

export type MetricTypeKey =
  | 'metricTemplate.metricType.gauge'
  | 'metricTemplate.metricType.counter'
  | 'metricTemplate.metricType.state'
  | 'metricTemplate.metricType.event';

export type MetricTypeOptionKey =
  | 'metricTemplate.metricTypeOption.gauge'
  | 'metricTemplate.metricTypeOption.counter'
  | 'metricTemplate.metricTypeOption.state'
  | 'metricTemplate.metricTypeOption.event';

export const METRIC_TYPE_LABEL_KEYS: Record<string, MetricTypeKey> = {
  gauge: 'metricTemplate.metricType.gauge',
  counter: 'metricTemplate.metricType.counter',
  state: 'metricTemplate.metricType.state',
  event: 'metricTemplate.metricType.event'
};

const METRIC_TYPE_OPTION_KEYS: { value: string; key: MetricTypeOptionKey }[] = [
  { value: 'gauge', key: 'metricTemplate.metricTypeOption.gauge' },
  { value: 'counter', key: 'metricTemplate.metricTypeOption.counter' },
  { value: 'state', key: 'metricTemplate.metricTypeOption.state' },
  { value: 'event', key: 'metricTemplate.metricTypeOption.event' }
];

export const SOURCE_LABEL: Record<string, string> = {
  snmp: 'SNMP',
  ipmi: 'IPMI',
  zabbix: 'Zabbix'
};

export const SOURCE_OPTIONS = [
  { label: 'SNMP', value: 'snmp' },
  { label: 'IPMI', value: 'ipmi' },
  { label: 'Zabbix', value: 'zabbix' }
];

export const deviceTypeLabel = (v: string, td: TFunction<'device'>): string => {
  const key = DEVICE_TYPE_LABEL_KEYS[v];
  return key ? td(key) : v;
};

export const metricTypeLabel = (v: string, t: TFunction<'monitor'>): string => {
  const key = METRIC_TYPE_LABEL_KEYS[v];
  return key ? t(key) : v;
};

export const buildDeviceTypeOptions = (td: TFunction<'device'>) =>
  (['network', 'server', 'other'] as const).map((value) => ({
    label: deviceTypeLabel(value, td),
    value
  }));

export const buildMetricTypeOptions = (t: TFunction<'monitor'>) =>
  METRIC_TYPE_OPTION_KEYS.map(({ value, key }) => ({ label: t(key), value }));

export interface MetricTemplateFormValues {
  device_type: string;
  metric_key: string;
  category?: string;
  display_name?: string;
  vendor?: string;
  source: string;
  mib?: string;
  oid_symbol?: string;
  oid?: string;
  zabbix_item_key?: string;
  index_kind?: string;
  metric_type: string;
  unit?: string;
  poll_interval?: number;
  warn?: number;
  crit?: number;
  expected?: string;
  threshold_json?: string; // event 类型用自由 JSON
  severity_default?: string;
  enabled?: boolean;
  description?: string;
  runbook_url?: string;
  runbook_title?: string;
}

export function buildThreshold(values: MetricTemplateFormValues): Record<string, unknown> | null {
  if (values.metric_type === 'gauge' || values.metric_type === 'counter') {
    const t: Record<string, unknown> = {};
    if (values.warn !== undefined && values.warn !== null) t.warn = values.warn;
    if (values.crit !== undefined && values.crit !== null) t.crit = values.crit;
    return Object.keys(t).length > 0 ? t : null;
  }
  if (values.metric_type === 'state') {
    return values.expected ? { expected: values.expected } : null;
  }
  if (values.threshold_json) {
    try {
      return JSON.parse(values.threshold_json);
    } catch {
      return null;
    }
  }
  return null;
}

export function parseThreshold(
  threshold: Record<string, unknown> | null | undefined,
  metricType: string
): Partial<MetricTemplateFormValues> {
  if (!threshold) return {};
  if (metricType === 'gauge' || metricType === 'counter') {
    return {
      warn: threshold.warn !== undefined ? Number(threshold.warn) : undefined,
      crit: threshold.crit !== undefined ? Number(threshold.crit) : undefined
    };
  }
  if (metricType === 'state') {
    return { expected: threshold.expected !== undefined ? String(threshold.expected) : undefined };
  }
  return { threshold_json: JSON.stringify(threshold, null, 2) };
}

export function renderThreshold(
  threshold: Record<string, unknown> | null | undefined,
  metricType: string,
  t: TFunction<'monitor'>
): React.ReactNode {
  const notConfigured = <Text type="secondary">{t('metricTemplate.threshold.notConfigured')}</Text>;
  if (!threshold) return notConfigured;
  if (metricType === 'gauge' || metricType === 'counter') {
    const parts: string[] = [];
    if (threshold.warn !== undefined) {
      parts.push(t('metricTemplate.threshold.warnAt', { value: String(threshold.warn) }));
    }
    if (threshold.crit !== undefined) {
      parts.push(t('metricTemplate.threshold.critAt', { value: String(threshold.crit) }));
    }
    return parts.length > 0 ? <Text>{parts.join(' / ')}</Text> : notConfigured;
  }
  if (metricType === 'state') {
    return threshold.expected !== undefined ? (
      <Text>
        {t('metricTemplate.threshold.expected', { value: String(threshold.expected) })}
      </Text>
    ) : (
      notConfigured
    );
  }
  return (
    <Text code style={{ fontSize: 12 }}>
      {JSON.stringify(threshold)}
    </Text>
  );
}
