/**
 * 指标模板共享常量与工具函数
 *
 * 从 MetricTemplates/index.tsx 拆分（M27）：表单与表格共用的标签映射、
 * 选项列表、阈值结构化转换与友好展示。
 */
import { Typography } from 'antd';

const { Text } = Typography;

export const DEVICE_TYPE_LABEL: Record<string, string> = {
  network: '网络设备',
  server: '服务器',
  other: '其他'
};

export const SOURCE_LABEL: Record<string, string> = {
  snmp: 'SNMP',
  ipmi: 'IPMI',
  zabbix: 'Zabbix'
};

export const METRIC_TYPE_LABEL: Record<string, string> = {
  gauge: '瞬时值',
  counter: '累加计数',
  state: '状态',
  event: '事件'
};

export const DEVICE_TYPE_OPTIONS = [
  { label: '网络设备', value: 'network' },
  { label: '服务器', value: 'server' },
  { label: '其他', value: 'other' }
];

export const SOURCE_OPTIONS = [
  { label: 'SNMP', value: 'snmp' },
  { label: 'IPMI', value: 'ipmi' },
  { label: 'Zabbix', value: 'zabbix' }
];

export const METRIC_TYPE_OPTIONS = [
  { label: '瞬时值（gauge）', value: 'gauge' },
  { label: '累加计数（counter）', value: 'counter' },
  { label: '状态（state）', value: 'state' },
  { label: '事件（event）', value: 'event' }
];

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
  metricType: string
): React.ReactNode {
  if (!threshold) return <Text type="secondary">未配置</Text>;
  if (metricType === 'gauge' || metricType === 'counter') {
    const parts: string[] = [];
    if (threshold.warn !== undefined) parts.push(`告警≥${threshold.warn}`);
    if (threshold.crit !== undefined) parts.push(`严重≥${threshold.crit}`);
    return parts.length > 0 ? (
      <Text>{parts.join(' / ')}</Text>
    ) : (
      <Text type="secondary">未配置</Text>
    );
  }
  if (metricType === 'state') {
    return threshold.expected !== undefined ? (
      <Text>期望={String(threshold.expected)}</Text>
    ) : (
      <Text type="secondary">未配置</Text>
    );
  }
  return (
    <Text code style={{ fontSize: 12 }}>
      {JSON.stringify(threshold)}
    </Text>
  );
}
