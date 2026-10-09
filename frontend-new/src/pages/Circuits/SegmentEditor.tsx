import { useEffect, useDeferredValue, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography
} from 'antd';
import { DeleteOutlined, PlusOutlined, SortAscendingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { useMessage } from '@/hooks/useMessage';
import { useNetworkDeviceOptions } from '@/services/device';
import { useNetworkPorts } from '@/services/network-port';
import { fetchPortLinks } from '@/services/device-connection';
import { queryKeys } from '@/services/query-keys';
import { ANCHOR_TAG_COLOR, resolveAnchorState } from './circuitMeta';
import {
  useCircuitSegments,
  useReplaceCircuitSegments,
  type CircuitSegment
} from '@/services/circuit';

type SegmentDraft = Pick<
  CircuitSegment,
  'seq' | 'connection_id' | 'device_id' | 'port_id' | 'hop_desc' | 'notes'
>;

interface SegmentRow extends SegmentDraft {
  key: string;
  anchor_lost: boolean;
}

function toRow(s: CircuitSegment): SegmentRow {
  return {
    key: String(s.id ?? s.seq),
    seq: s.seq,
    connection_id: s.connection_id ?? null,
    device_id: s.device_id ?? null,
    port_id: s.port_id ?? null,
    hop_desc: s.hop_desc ?? '',
    notes: s.notes ?? '',
    anchor_lost: s.anchor_lost
  };
}

function emptyRow(seq: number, key: string): SegmentRow {
  return {
    key,
    seq,
    connection_id: null,
    device_id: null,
    port_id: null,
    hop_desc: '',
    notes: '',
    anchor_lost: false
  };
}

interface SegmentEditorProps {
  circuitId: number | null;
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

function DeviceSelect({
  value,
  onChange
}: {
  value: number | null;
  onChange: (id: number | null) => void;
}) {
  const { t } = useTranslation('circuit');
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const options = useNetworkDeviceOptions(deferredSearch || undefined);
  const merged =
    value && !options.some((o) => o.value === value)
      ? [{ label: `#${value}（${t('segment.deviceMissing')}）`, value }, ...options]
      : options;
  return (
    <Select
      value={value ?? undefined}
      onChange={(v) => onChange(v ?? null)}
      options={merged}
      showSearch
      onSearch={setSearch}
      filterOption={false}
      allowClear
      size="small"
      style={{ width: '100%' }}
      placeholder={t('segment.selectDevice')}
    />
  );
}

function DevicePortSelect({
  deviceId,
  value,
  onChange
}: {
  deviceId: number | null;
  value: number | null;
  onChange: (portId: number | null, connectionId: number | null) => void;
}) {
  const { t } = useTranslation('circuit');
  const queryClient = useQueryClient();
  const latestReq = useRef<{ pid: number | null }>({ pid: null });
  const { data: ports } = useNetworkPorts(deviceId ?? 0, { enabled: !!deviceId });
  const options = (ports ?? []).map((p) => ({ label: p.port_name, value: p.id }));
  const merged =
    value && !options.some((o) => o.value === value)
      ? [{ label: `#${value}（${t('segment.portMissing')}）`, value }, ...options]
      : options;

  const handleChange = async (pid: number | null) => {
    latestReq.current.pid = pid;
    if (!deviceId || !pid) {
      onChange(pid ?? null, null);
      return;
    }
    const links = await queryClient.fetchQuery({
      queryKey: [...queryKeys.devices.detail(deviceId), 'port-links'],
      queryFn: () => fetchPortLinks(deviceId)
    });
    if (latestReq.current.pid !== pid) return;
    const hit = links.find((pl) => pl.local_port_id === pid);
    onChange(pid, hit ? hit.id : null);
  };

  return (
    <Select
      value={value ?? undefined}
      onChange={(v) => void handleChange(v ?? null)}
      options={merged}
      showSearch
      optionFilterProp="label"
      allowClear
      size="small"
      disabled={!deviceId}
      style={{ width: '100%' }}
      placeholder={deviceId ? undefined : t('segment.selectDeviceFirst')}
    />
  );
}

function SegmentEditor({ circuitId, open, onCancel, onSuccess }: SegmentEditorProps) {
  const { t } = useTranslation('circuit');
  const message = useMessage();
  const navigate = useNavigate();

  const { data: segments, isLoading } = useCircuitSegments(circuitId);
  const replaceSegments = useReplaceCircuitSegments();

  const [rows, setRows] = useState<SegmentRow[]>([]);

  const initializedFor = useRef<number | null>(null);

  useEffect(() => {
    if (!open) {
      initializedFor.current = null;
      return;
    }
    if (initializedFor.current === circuitId) return;
    if (!segments) return; // 等首次数据到位再建草稿
    setRows(segments.map(toRow));
    initializedFor.current = circuitId;
  }, [open, circuitId, segments]);

  const seqError = useMemo(() => {
    if (rows.length === 0) return null;
    const seqs = rows.map((r) => r.seq);
    if (new Set(seqs).size !== seqs.length) return t('segment.error.seqDuplicate');
    const sorted = [...seqs].sort((a, b) => a - b);
    if (sorted[0] !== 1) return t('segment.error.seqNotFromOne');
    for (let i = 1; i < sorted.length; i += 1) {
      if (sorted[i] !== sorted[i - 1] + 1) return t('segment.error.seqHole');
    }
    return null;
  }, [rows, t]);

  const patch = (key: string, field: keyof SegmentDraft | 'anchor_lost', value: unknown) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
  };

  const newRowSeq = useRef(0);

  const addRow = () =>
    setRows((prev) => {
      newRowSeq.current += 1;
      return [...prev, emptyRow(prev.length + 1, `new-${newRowSeq.current}`)];
    });

  const removeRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));

  const resort = () => setRows((prev) => prev.map((r, i) => ({ ...r, seq: i + 1 })));

  const handleSubmit = async () => {
    if (!circuitId) return;
    if (seqError) {
      message.error(seqError);
      return;
    }
    const payload: SegmentDraft[] = rows.map((r) => ({
      seq: r.seq,
      connection_id: r.connection_id ?? null,
      device_id: r.device_id ?? null,
      port_id: r.port_id ?? null,
      hop_desc: r.hop_desc || null,
      notes: r.notes || null
    }));
    try {
      await replaceSegments.mutateAsync({ id: circuitId, segments: payload });
      message.success(t('segment.message.saveSuccess'));
      onSuccess();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('segment.message.saveFailed'));
    }
  };

  const columns = [
    {
      title: t('segment.field.seq'),
      dataIndex: 'seq',
      key: 'seq',
      width: 80,
      render: (v: number, r: SegmentRow) => (
        <InputNumber
          min={1}
          value={v}
          size="small"
          onChange={(n) => patch(r.key, 'seq', n ?? 0)}
          style={{ width: '100%' }}
        />
      )
    },
    {
      title: t('segment.field.connectionId'),
      dataIndex: 'connection_id',
      key: 'connection_id',
      width: 130,
      render: (v: number | null, r: SegmentRow) => {
        const state = resolveAnchorState(r);
        const clickable = state === 'managed' && r.device_id != null;
        return (
          <Space size={4} wrap>
            <Tag
              color={ANCHOR_TAG_COLOR[state]}
              style={clickable ? { cursor: 'pointer' } : undefined}
              onClick={
                clickable ? () => navigate(`/devices/${r.device_id}#connections`) : undefined
              }
            >
              {state === 'managed'
                ? t('segment.anchorConnection', { id: v })
                : state === 'lost'
                  ? t('segment.anchorLost')
                  : t('segment.notManaged')}
            </Tag>
          </Space>
        );
      }
    },
    {
      title: t('segment.field.deviceId'),
      dataIndex: 'device_id',
      key: 'device_id',
      width: 170,
      render: (v: number | null, r: SegmentRow) => (
        <DeviceSelect
          value={v}
          onChange={(id) => {
            patch(r.key, 'device_id', id);
            patch(r.key, 'port_id', null);
            patch(r.key, 'connection_id', null);
            patch(r.key, 'anchor_lost', false);
          }}
        />
      )
    },
    {
      title: t('segment.field.portId'),
      dataIndex: 'port_id',
      key: 'port_id',
      width: 130,
      render: (v: number | null, r: SegmentRow) => (
        <DevicePortSelect
          deviceId={r.device_id}
          value={v}
          onChange={(pid, connId) => {
            patch(r.key, 'port_id', pid);
            patch(r.key, 'connection_id', connId);
            patch(r.key, 'anchor_lost', false);
          }}
        />
      )
    },
    {
      title: t('segment.field.hopDesc'),
      dataIndex: 'hop_desc',
      key: 'hop_desc',
      render: (v: string, r: SegmentRow) => (
        <Input
          value={v}
          size="small"
          placeholder={t('segment.hopDescPlaceholder')}
          onChange={(e) => patch(r.key, 'hop_desc', e.target.value)}
        />
      )
    },
    {
      title: t('field.notes'),
      dataIndex: 'notes',
      key: 'notes',
      width: 160,
      render: (v: string, r: SegmentRow) => (
        <Input value={v} size="small" onChange={(e) => patch(r.key, 'notes', e.target.value)} />
      )
    },
    {
      title: '',
      key: 'op',
      width: 56,
      render: (_: unknown, r: SegmentRow) => (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => removeRow(r.key)}
        />
      )
    }
  ];

  return (
    <Drawer
      open={open}
      onClose={onCancel}
      width={960}
      destroyOnHidden
      title={t('segment.title')}
      extra={
        <Space wrap>
          <Button icon={<SortAscendingOutlined />} onClick={resort}>
            {t('segment.action.resort')}
          </Button>
          <Button icon={<PlusOutlined />} onClick={addRow}>
            {t('segment.action.add')}
          </Button>
          <Button type="primary" loading={replaceSegments.isPending} onClick={handleSubmit}>
            {t('segment.action.save')}
          </Button>
        </Space>
      }
    >
      {seqError && <Alert type="error" showIcon message={seqError} style={{ marginBottom: 12 }} />}
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        {t('segment.hint')}
      </Typography.Paragraph>
      <Table<SegmentRow>
        columns={columns}
        dataSource={rows}
        rowKey="key"
        size="small"
        loading={isLoading}
        pagination={false}
        locale={{ emptyText: t('segment.empty') }}
      />
    </Drawer>
  );
}

export default SegmentEditor;
