/**
 * 监控总览 - 设备监控状态表（含批量探测 / 批量启停 / 单设备探测冷却）
 *
 * 从 Overview 拆分（M28）：保留所有交互逻辑（mutation + 批量选择 + 冷却计时）。
 */
import { useState, useEffect, useCallback, memo } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Segmented,
  Tooltip,
  Typography,
  Switch,
  Input
} from 'antd';
import {
  ThunderboltOutlined,
  ReloadOutlined,
  PoweroffOutlined,
  EyeInvisibleOutlined
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { MONITOR_PROTOCOL_COLOR_MAP } from '@/types/enums';
import {
  useMonitorStatuses,
  useCheckDeviceNow,
  useCheckBatchDevices,
  useToggleDeviceMonitor,
  useBatchToggleDeviceMonitor,
  type MonitorStatusFilter,
  type MonitorStatusItem
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import DataTable from '@/components/DataTable';
import BatchActionBar from '@/components/BatchActionBar/BatchActionBar';
import MetricAlertPopover from '@/components/Monitor/MetricAlertPopover';
import { relativeTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const { Text } = Typography;

const getFilterOptions = (t: TFunction<'monitor'>) => [
  { label: t('filter.all'), value: '' },
  { label: t('deviceStatus.filter.connectivity'), value: 'unreachable' },
  { label: t('deviceStatus.filter.metricAlerting'), value: 'metric_alerting' },
  { label: t('deviceStatus.filter.interrupted'), value: 'interrupted' },
  { label: t('status.blindspot'), value: 'blindspot' }
];

const PROBE_COOLDOWN_SECONDS = 30;

const CooldownButton = memo(function CooldownButton({
  deviceId,
  cooldownEnd,
  isProbing,
  probeLabel,
  onProbe
}: {
  deviceId: number;
  cooldownEnd: number;
  isProbing: boolean;
  probeLabel: string;
  onProbe: (id: number) => void;
}) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    const update = () => {
      const r = cooldownEnd ? Math.max(0, Math.ceil((cooldownEnd - Date.now()) / 1000)) : 0;
      setRemaining(r);
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [cooldownEnd]);

  return (
    <Button
      size="small"
      icon={<ThunderboltOutlined />}
      loading={isProbing}
      disabled={remaining > 0 && !isProbing}
      onClick={() => onProbe(deviceId)}
    >
      {remaining > 0 && !isProbing ? `${remaining}s` : probeLabel}
    </Button>
  );
});

export default function DeviceStatusTable() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const checkDevice = useCheckDeviceNow();
  const checkBatch = useCheckBatchDevices();
  const toggleMonitor = useToggleDeviceMonitor();
  const batchToggleMonitor = useBatchToggleDeviceMonitor();
  const message = useMessage();
  const table = useTable();

  const [statusFilter, setStatusFilter] = useState<MonitorStatusFilter>(undefined);
  const [keyword, setKeyword] = useState('');
  const [probingId, setProbingId] = useState<number | null>(null);
  const [cooldownMap, setCooldownMap] = useState<Record<number, number>>({});

  const { data: statusData, isLoading: statusesLoading } = useMonitorStatuses({
    status_filter: statusFilter,
    page: table.page,
    per_page: table.perPage,
    keyword: keyword || undefined
  });

  const batch = useBatchSelection<MonitorStatusItem>({
    dataSource: statusData?.items ?? [],
    getRowKey: (r) => String(r.device_id)
  });

  const handleProbe = useCallback(
    async (deviceId: number) => {
      setProbingId(deviceId);
      try {
        const result = await checkDevice.mutateAsync(deviceId);
        if (result.reachable) {
          message.success(t('deviceStatus.probe.success', { value: result.latency_ms ?? '—' }));
        } else {
          message.warning(
            t('deviceStatus.probe.failure', {
              error: result.error ?? t('deviceStatus.probe.unknownError')
            })
          );
        }
      } catch (err: unknown) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr?.response?.status === 429) {
          message.warning(t('deviceStatus.probe.coolingDown'));
        } else {
          message.error(
            err instanceof Error ? err.message : t('deviceStatus.probe.requestFailed')
          );
        }
      } finally {
        setProbingId(null);
        setCooldownMap((prev) => ({
          ...prev,
          [deviceId]: Date.now() + PROBE_COOLDOWN_SECONDS * 1000
        }));
      }
    },
    [checkDevice, message, t]
  );

  const handleBatchProbe = async () => {
    if (batch.count === 0) return;
    const ids = batch.selectedKeys.map((k) => Number(k));
    const hide = message.loading(t('deviceStatus.probe.probing', { count: ids.length }), 0);
    try {
      const res = await checkBatch.mutateAsync(ids);
      const reachable = res.results.filter((r) => r.reachable === true).length;
      const unreachable = res.results.filter((r) => r.reachable === false).length;
      const skipped = res.skipped?.length ?? 0;
      hide();
      if (skipped > 0) {
        message.success(
          t('deviceStatus.probe.completeWithSkipped', { reachable, unreachable, skipped })
        );
      } else {
        message.success(t('deviceStatus.probe.complete', { reachable, unreachable }));
      }
      batch.clear();
    } catch (err: unknown) {
      hide();
      message.error(err instanceof Error ? err.message : t('deviceStatus.probe.batchFailed'));
    }
  };

  const handleBatchToggleMonitor = async (enabled: boolean) => {
    if (batch.count === 0) return;
    const ids = batch.selectedKeys.map((k) => Number(k));
    const toggleKey = enabled ? 'enabled' : 'disabled';
    const hide = message.loading(
      t(`deviceStatus.probe.toggling.${toggleKey}`, { count: ids.length }),
      0
    );
    try {
      const res = await batchToggleMonitor.mutateAsync({ deviceIds: ids, enabled });
      hide();
      message.success(
        t(`deviceStatus.probe.toggleDone.${toggleKey}`, {
          count: res.updated,
          skipped: res.skipped
        })
      );
      batch.clear();
    } catch (err: unknown) {
      hide();
      message.error(
        err instanceof Error
          ? err.message
          : t(`deviceStatus.probe.batchToggleFailed.${toggleKey}`)
      );
    }
  };

  const handleToggleMonitorEnabled = async (deviceId: number, enabled: boolean) => {
    try {
      await toggleMonitor.mutateAsync({ deviceId, enabled });
      message.success(
        t(`deviceStatus.probe.toggleSingle.${enabled ? 'enabled' : 'disabled'}`)
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const columns = [
    {
      title: td('field.name'),
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: MonitorStatusItem) => (
        <Link to={`/devices/${record.device_id}`}>{name || `#${record.device_id}`}</Link>
      )
    },
    {
      title: tc('field.type'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (deviceType: string) => <Tag>{deviceType}</Tag>
    },
    {
      title: t('column.managementIp'),
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      render: (ip: string | null) => ip || '—'
    },
    {
      title: t('column.protocol'),
      dataIndex: 'protocol',
      key: 'protocol',
      width: 90,
      render: (p: string) => (
        <Tag color={MONITOR_PROTOCOL_COLOR_MAP[p] || 'default'}>{p?.toUpperCase()}</Tag>
      )
    },
    {
      title: t('column.connectivity'),
      key: 'reachable',
      width: 110,
      render: (_: unknown, record: MonitorStatusItem) => {
        if (record.alert_blindspot) {
          return (
            <Tooltip title={t('status.blindspotTooltip')}>
              <Tag color="red" icon={<EyeInvisibleOutlined />}>
                {t('status.blindspotShort')}
              </Tag>
            </Tooltip>
          );
        }
        if (record.monitor_interrupted)
          return <Tag color="orange">{t('deviceStatus.filter.interrupted')}</Tag>;
        if (record.reachable) return <Tag color="success">{t('status.connected')}</Tag>;
        if (record.down_alerted) return <Tag color="error">{t('status.unreachable')}</Tag>;
        if (record.consecutive_failures > 0)
          return <Tag color="warning">{t('status.flapping')}</Tag>;
        return <Tag>{tc('field.unknown')}</Tag>;
      }
    },
    {
      title: t('column.metricAlert'),
      key: 'metric_alerts',
      width: 130,
      render: (_: unknown, record: MonitorStatusItem) => (
        <MetricAlertPopover
          deviceId={record.device_id}
          alertCount={record.active_metric_alerts ?? 0}
          maxSeverity={record.max_alert_severity ?? 0}
        />
      )
    },
    {
      title: td('field.monitor'),
      key: 'monitor_enabled',
      width: 80,
      align: 'center' as const,
      render: (_: unknown, record: MonitorStatusItem) => (
        <Tooltip
          title={
            record.monitor_enabled === false
              ? t('status.probePaused')
              : t('status.probeNormal')
          }
        >
          <Switch
            size="small"
            checked={record.monitor_enabled !== false}
            loading={
              toggleMonitor.isPending && toggleMonitor.variables?.deviceId === record.device_id
            }
            onChange={(checked) => handleToggleMonitorEnabled(record.device_id, checked)}
          />
        </Tooltip>
      )
    },
    {
      title: t('column.failureCount'),
      dataIndex: 'consecutive_failures',
      key: 'consecutive_failures',
      width: 90,
      align: 'center' as const,
      render: (n: number) => (n > 0 ? <Text type="danger">{n}</Text> : '—')
    },
    {
      title: t('column.lastCheck'),
      dataIndex: 'last_checked_at',
      key: 'last_checked_at',
      width: 110,
      render: (v: string | null) => relativeTime(v, tc)
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: MonitorStatusItem) => (
        <CooldownButton
          deviceId={record.device_id}
          cooldownEnd={cooldownMap[record.device_id] ?? 0}
          isProbing={probingId === record.device_id}
          probeLabel={t('deviceStatus.probe.action')}
          onProbe={handleProbe}
        />
      )
    }
  ];

  return (
    <Card
      title={t('deviceStatus.title')}
      extra={
        <Space>
          <Input.Search
            allowClear
            placeholder={t('deviceStatus.searchPlaceholder')}
            style={{ width: 220 }}
            onSearch={(v) => {
              setKeyword(v);
              table.setPage(1);
            }}
          />
          <Segmented
            options={getFilterOptions(t)}
            value={statusFilter || ''}
            onChange={(v) => {
              setStatusFilter((v || undefined) as MonitorStatusFilter);
              table.setPage(1);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => table.setPage(table.page)}>
            {tc('action.refresh')}
          </Button>
        </Space>
      }
    >
      <BatchActionBar
        count={batch.count}
        unit={t('stat.unitDevice', { count: batch.count })}
        onClear={batch.clear}
      >
        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={checkBatch.isPending}
          onClick={handleBatchProbe}
        >
          {t('deviceStatus.batch.probe')}
        </Button>
        <Button
          size="small"
          icon={<PoweroffOutlined />}
          loading={batchToggleMonitor.isPending}
          onClick={() => handleBatchToggleMonitor(true)}
        >
          {t('deviceStatus.batch.enableMonitor')}
        </Button>
        <Button
          size="small"
          danger
          icon={<PoweroffOutlined />}
          loading={batchToggleMonitor.isPending}
          onClick={() => handleBatchToggleMonitor(false)}
        >
          {t('deviceStatus.batch.pauseMonitor')}
        </Button>
      </BatchActionBar>
      <DataTable<MonitorStatusItem>
        columns={columns}
        dataSource={statusData?.items ?? []}
        loading={statusesLoading}
        rowKey={(r) => String(r.device_id)}
        rowSelection={batch.rowSelection}
        total={statusData?.total ?? 0}
        searchable={false}
        showCard={false}
        tableProps={table}
      />
    </Card>
  );
}
