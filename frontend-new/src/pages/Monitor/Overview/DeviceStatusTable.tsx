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

const { Text } = Typography;

const FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '连通异常', value: 'unreachable' },
  { label: '指标告警', value: 'metric_alerting' },
  { label: '监控中断', value: 'interrupted' },
  { label: '告警盲区', value: 'blindspot' }
];

const PROBE_COOLDOWN_SECONDS = 30;

const CooldownButton = memo(function CooldownButton({
  deviceId,
  cooldownEnd,
  isProbing,
  onProbe
}: {
  deviceId: number;
  cooldownEnd: number;
  isProbing: boolean;
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
      {remaining > 0 && !isProbing ? `${remaining}s` : '探测'}
    </Button>
  );
});

export default function DeviceStatusTable() {
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
          message.success(`探测成功，延迟 ${result.latency_ms ?? '—'} ms`);
        } else {
          message.warning(`探测失败：${result.error ?? '未知错误'}`);
        }
      } catch (err: unknown) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr?.response?.status === 429) {
          message.warning('该设备探测冷却中，请稍后再试');
        } else {
          message.error(err instanceof Error ? err.message : '探测请求失败');
        }
      } finally {
        setProbingId(null);
        setCooldownMap((prev) => ({
          ...prev,
          [deviceId]: Date.now() + PROBE_COOLDOWN_SECONDS * 1000
        }));
      }
    },
    [checkDevice, message]
  );

  const handleBatchProbe = async () => {
    if (batch.count === 0) return;
    const ids = batch.selectedKeys.map((k) => Number(k));
    const hide = message.loading(`正在探测 ${ids.length} 台设备...`, 0);
    try {
      const res = await checkBatch.mutateAsync(ids);
      const reachable = res.results.filter((r) => r.reachable === true).length;
      const unreachable = res.results.filter((r) => r.reachable === false).length;
      const skipped = res.skipped?.length ?? 0;
      hide();
      if (skipped > 0) {
        message.success(
          `探测完成：可达 ${reachable} 台，不可达 ${unreachable} 台，跳过（冷却/不存在）${skipped} 台`
        );
      } else {
        message.success(`探测完成：可达 ${reachable} 台，不可达 ${unreachable} 台`);
      }
      batch.clear();
    } catch (err: unknown) {
      hide();
      message.error(err instanceof Error ? err.message : '批量探测请求失败');
    }
  };

  const handleBatchToggleMonitor = async (enabled: boolean) => {
    if (batch.count === 0) return;
    const ids = batch.selectedKeys.map((k) => Number(k));
    const action = enabled ? '开启' : '暂停';
    const hide = message.loading(`正在${action} ${ids.length} 台设备的监控...`, 0);
    try {
      const res = await batchToggleMonitor.mutateAsync({ deviceIds: ids, enabled });
      hide();
      message.success(`已${action} ${res.updated} 台设备监控，跳过 ${res.skipped} 台`);
      batch.clear();
    } catch (err: unknown) {
      hide();
      message.error(err instanceof Error ? err.message : `批量${action}监控失败`);
    }
  };

  const handleToggleMonitorEnabled = async (deviceId: number, enabled: boolean) => {
    try {
      await toggleMonitor.mutateAsync({ deviceId, enabled });
      message.success(enabled ? '已恢复该设备监控' : '已暂停该设备监控');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const columns = [
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: MonitorStatusItem) => (
        <Link to={`/devices/${record.device_id}`}>{name || `#${record.device_id}`}</Link>
      )
    },
    {
      title: '类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (t: string) => <Tag>{t}</Tag>
    },
    {
      title: '管理IP',
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      render: (ip: string | null) => ip || '—'
    },
    {
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 90,
      render: (p: string) => (
        <Tag color={MONITOR_PROTOCOL_COLOR_MAP[p] || 'default'}>{p?.toUpperCase()}</Tag>
      )
    },
    {
      title: '连通状态',
      key: 'reachable',
      width: 110,
      render: (_: unknown, record: MonitorStatusItem) => {
        if (record.alert_blindspot) {
          return (
            <Tooltip title="告警已触发但无接收人">
              <Tag color="red" icon={<EyeInvisibleOutlined />}>
                盲区
              </Tag>
            </Tooltip>
          );
        }
        if (record.monitor_interrupted) return <Tag color="orange">监控中断</Tag>;
        if (record.reachable) return <Tag color="success">连通</Tag>;
        if (record.down_alerted) return <Tag color="error">不可达</Tag>;
        if (record.consecutive_failures > 0) return <Tag color="warning">抖动</Tag>;
        return <Tag>未知</Tag>;
      }
    },
    {
      title: '指标告警',
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
      title: '监控',
      key: 'monitor_enabled',
      width: 80,
      align: 'center' as const,
      render: (_: unknown, record: MonitorStatusItem) => (
        <Tooltip title={record.monitor_enabled === false ? '已暂停探测' : '正常探测'}>
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
      title: '失败次数',
      dataIndex: 'consecutive_failures',
      key: 'consecutive_failures',
      width: 90,
      align: 'center' as const,
      render: (n: number) => (n > 0 ? <Text type="danger">{n}</Text> : '—')
    },
    {
      title: '最近检查',
      dataIndex: 'last_checked_at',
      key: 'last_checked_at',
      width: 110,
      render: relativeTime
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: MonitorStatusItem) => (
        <CooldownButton
          deviceId={record.device_id}
          cooldownEnd={cooldownMap[record.device_id] ?? 0}
          isProbing={probingId === record.device_id}
          onProbe={handleProbe}
        />
      )
    }
  ];

  return (
    <Card
      title="设备监控状态"
      extra={
        <Space>
          <Input.Search
            allowClear
            placeholder="搜索设备名 / IP / BMC"
            style={{ width: 220 }}
            onSearch={(v) => {
              setKeyword(v);
              table.setPage(1);
            }}
          />
          <Segmented
            options={FILTER_OPTIONS}
            value={statusFilter || ''}
            onChange={(v) => {
              setStatusFilter((v || undefined) as MonitorStatusFilter);
              table.setPage(1);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => table.setPage(table.page)}>
            刷新
          </Button>
        </Space>
      }
    >
      <BatchActionBar count={batch.count} unit="台设备" onClear={batch.clear}>
        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={checkBatch.isPending}
          onClick={handleBatchProbe}
        >
          批量探测
        </Button>
        <Button
          size="small"
          icon={<PoweroffOutlined />}
          loading={batchToggleMonitor.isPending}
          onClick={() => handleBatchToggleMonitor(true)}
        >
          批量开启监控
        </Button>
        <Button
          size="small"
          danger
          icon={<PoweroffOutlined />}
          loading={batchToggleMonitor.isPending}
          onClick={() => handleBatchToggleMonitor(false)}
        >
          批量暂停监控
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
