import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Descriptions,
  Drawer,
  Empty,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography
} from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useResponsive } from '@/hooks/useResponsive';

import {
  useCircuitDetail,
  useCircuitDevices,
  useCircuitImpactByConnection,
  useCircuitSegments,
  type Circuit,
  type CircuitSegment
} from '@/services/circuit';
import {
  ANCHOR_TAG_COLOR,
  BILLING_MODE_KEY,
  CIRCUIT_STATUS_COLOR,
  CIRCUIT_STATUS_KEY,
  resolveAnchorState
} from './circuitMeta';
import SegmentEditor from './SegmentEditor';

interface CircuitDetailProps {
  circuitId: number | null;
  open: boolean;
  onClose: () => void;
}

function CircuitDetail({ circuitId, open, onClose }: CircuitDetailProps) {
  const { t } = useTranslation('circuit');
  const { t: tc } = useTranslation('common');
  const { isMobile } = useResponsive();
  const navigate = useNavigate();

  const { data: circuit, isLoading } = useCircuitDetail(circuitId);
  const { data: segments } = useCircuitSegments(circuitId);
  const { data: devices } = useCircuitDevices(circuitId);

  const [editorOpen, setEditorOpen] = useState(false);

  const connectionIds = useMemo(
    () => [
      ...new Set(
        (segments ?? [])
          .map((s) => s.connection_id)
          .filter((v): v is number => typeof v === 'number')
      )
    ],
    [segments]
  );

  const [selectedConn, setSelectedConn] = useState<number | null>(null);

  useEffect(() => {
    setSelectedConn((prev) =>
      prev && connectionIds.includes(prev) ? prev : (connectionIds[0] ?? null)
    );
  }, [connectionIds]);

  const { data: impact } = useCircuitImpactByConnection(selectedConn);

  const segmentColumns = useMemo(
    () => [
      { title: t('segment.field.seq'), dataIndex: 'seq', key: 'seq', width: 64 },
      {
        title: t('segment.field.connectionId'),
        key: 'connection_id',
        width: 150,
        render: (_: unknown, r: CircuitSegment) => {
          const state = resolveAnchorState(r);
          const clickable = state === 'managed' && r.device_id != null;
          return (
            <Tag
              color={ANCHOR_TAG_COLOR[state]}
              style={clickable ? { cursor: 'pointer' } : undefined}
              onClick={
                clickable ? () => navigate(`/devices/${r.device_id}#connections`) : undefined
              }
            >
              {state === 'managed'
                ? t('segment.anchorConnection', { id: r.connection_id })
                : state === 'lost'
                  ? t('segment.anchorLost')
                  : t('segment.notManaged')}
            </Tag>
          );
        }
      },
      {
        title: t('segment.field.deviceId'),
        dataIndex: 'device_id',
        key: 'device_id',
        width: 170,
        render: (v: number | null, r: CircuitSegment) => {
          if (v == null) return '-';
          return r.device_name ?? `#${v}（${t('segment.deviceMissing')}）`;
        }
      },
      {
        title: t('segment.field.portId'),
        dataIndex: 'port_id',
        key: 'port_id',
        width: 120,
        render: (v: number | null, r: CircuitSegment) => {
          if (v == null) return '-';
          return r.port_name ?? `#${v}（${t('segment.portMissing')}）`;
        }
      },
      {
        title: t('segment.field.hopDesc'),
        dataIndex: 'hop_desc',
        key: 'hop_desc',
        render: (v: string | null) => v ?? '-'
      },
      {
        title: t('field.notes'),
        dataIndex: 'notes',
        key: 'notes',
        render: (v: string | null) => v ?? '-'
      }
    ],
    [t, navigate]
  );

  const deviceColumns = useMemo(
    () => [
      { title: tc('field.name'), dataIndex: 'device_name', key: 'device_name' },
      { title: t('detail.hostname'), dataIndex: 'hostname', key: 'hostname' }
    ],
    [t, tc]
  );

  const impactColumns = useMemo(
    () => [
      { title: t('field.circuitNo'), dataIndex: 'circuit_no', key: 'circuit_no', width: 160 },
      { title: tc('field.name'), dataIndex: 'name', key: 'name' },
      {
        title: t('field.status'),
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: Circuit['status']) =>
          v ? (
            <Tag color={CIRCUIT_STATUS_COLOR[v] ?? 'default'}>{t(CIRCUIT_STATUS_KEY[v])}</Tag>
          ) : (
            '-'
          )
      },
      {
        title: t('field.customer'),
        dataIndex: 'customer_name',
        key: 'customer_name',
        render: (v: string | null) => v ?? '-'
      }
    ],
    [t, tc]
  );

  const detailItems = useMemo(() => {
    if (!circuit) return [];
    return [
      { key: 'circuit_no', label: t('field.circuitNo'), children: circuit.circuit_no },
      { key: 'name', label: tc('field.name'), children: circuit.name ?? '-' },
      { key: 'carrier', label: t('field.carrier'), children: circuit.carrier_name ?? '-' },
      { key: 'customer', label: t('field.customer'), children: circuit.customer_name ?? '-' },
      {
        key: 'status',
        label: t('field.status'),
        children: circuit.status ? (
          <Tag color={CIRCUIT_STATUS_COLOR[circuit.status] ?? 'default'}>
            {t(CIRCUIT_STATUS_KEY[circuit.status])}
          </Tag>
        ) : (
          '-'
        )
      },
      {
        key: 'bandwidth',
        label: t('field.bandwidth'),
        children: circuit.bandwidth_mbps != null ? `${circuit.bandwidth_mbps} Mbps` : '-'
      },
      {
        key: 'billing_mode',
        label: t('field.billingMode'),
        children: circuit.billing_mode ? t(BILLING_MODE_KEY[circuit.billing_mode]) : '-'
      },
      {
        key: 'committed',
        label: t('field.committed'),
        children: circuit.committed_is_derived
          ? t('detail.committedDerived')
          : circuit.committed_mbps != null
            ? `${circuit.committed_mbps} Mbps`
            : '-'
      },
      { key: 'monthly_fee', label: t('field.monthlyFee'), children: circuit.monthly_fee ?? '-' },
      {
        key: 'overage_unit_price',
        label: t('field.overagePrice'),
        children: circuit.overage_unit_price ?? '-'
      },
      {
        key: 'traffic_unit_price',
        label: t('field.trafficPrice'),
        children: circuit.traffic_unit_price ?? '-'
      },
      { key: 'access_type', label: t('field.accessType'), children: circuit.access_type ?? '-' },
      { key: 'sla', label: t('field.sla'), children: circuit.sla_level ?? '-' },
      { key: 'start_date', label: t('field.startDate'), children: circuit.start_date ?? '-' },
      { key: 'end_date', label: t('field.endDate'), children: circuit.end_date ?? '-' },
      { key: 'contract_no', label: t('field.contractNo'), children: circuit.contract_no ?? '-' },
      { key: 'a_end', label: t('field.aEnd'), children: circuit.a_end_desc ?? '-' },
      { key: 'z_end', label: t('field.zEnd'), children: circuit.z_end_desc ?? '-' },
      { key: 'notes', label: t('field.notes'), children: circuit.notes ?? '-' }
    ];
  }, [circuit, t, tc]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={isMobile ? '100vw' : 880}
      destroyOnHidden
      loading={isLoading}
      title={circuit ? `${t('detail.title')} · ${circuit.circuit_no}` : t('detail.title')}
    >
      {circuit && (
        <>
          <Descriptions column={{ xs: 1, md: 2 }} size="small" bordered items={detailItems} />

          <Tabs
            style={{ marginTop: 16 }}
            items={[
              {
                key: 'segments',
                label: t('detail.tab.segments'),
                children: (
                  <>
                    <Space style={{ marginBottom: 8 }} wrap>
                      <Button
                        type="primary"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => setEditorOpen(true)}
                      >
                        {t('segment.action.edit')}
                      </Button>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t('segment.hint')}
                      </Typography.Text>
                    </Space>
                    {/* 路由锚点三态图例：颜色与表格 Tag 同源（ANCHOR_TAG_COLOR），集中一处 */}
                    <Space size={8} style={{ marginBottom: 8 }} wrap>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t('segment.legend.label')}
                      </Typography.Text>
                      <Tag color={ANCHOR_TAG_COLOR.managed}>{t('segment.legend.managed')}</Tag>
                      <Tag color={ANCHOR_TAG_COLOR.notManaged}>
                        {t('segment.legend.notManaged')}
                      </Tag>
                      <Tag color={ANCHOR_TAG_COLOR.lost}>{t('segment.legend.lost')}</Tag>
                    </Space>
                    <Table<CircuitSegment>
                      columns={segmentColumns}
                      dataSource={segments ?? []}
                      rowKey={(r) => String(r.id ?? r.seq)}
                      size="small"
                      pagination={false}
                      scroll={{ x: 'max-content' }}
                      locale={{ emptyText: t('segment.empty') }}
                    />
                  </>
                )
              },
              {
                key: 'devices',
                label: t('detail.tab.devices'),
                children: (
                  <Table
                    columns={deviceColumns}
                    dataSource={devices ?? []}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    scroll={{ x: 'max-content' }}
                    locale={{ emptyText: t('detail.devicesEmpty') }}
                  />
                )
              },
              {
                key: 'impact',
                label: t('detail.tab.impact'),
                children:
                  connectionIds.length === 0 ? (
                    <Empty description={t('impact.noConnection')} />
                  ) : (
                    <>
                      <Space style={{ marginBottom: 8 }} wrap>
                        <span>{t('impact.pickConnection')}</span>
                        <Select
                          size="small"
                          style={{ width: isMobile ? '100%' : 180 }}
                          value={selectedConn ?? undefined}
                          onChange={setSelectedConn}
                          options={connectionIds.map((id) => ({ label: `#${id}`, value: id }))}
                        />
                        {impact && impact.shared_by != null && (
                          <Tag color={impact.shared_by > 1 ? 'warning' : 'default'}>
                            {t('impact.sharedBy', { count: impact.shared_by })}
                          </Tag>
                        )}
                      </Space>
                      <Table<Circuit>
                        columns={impactColumns}
                        dataSource={impact?.items ?? []}
                        rowKey="id"
                        size="small"
                        pagination={false}
                        scroll={{ x: 'max-content' }}
                        locale={{ emptyText: t('impact.empty') }}
                      />
                    </>
                  )
              }
            ]}
          />

          <SegmentEditor
            circuitId={circuitId}
            open={editorOpen}
            onCancel={() => setEditorOpen(false)}
            onSuccess={() => setEditorOpen(false)}
          />
        </>
      )}
    </Drawer>
  );
}

export default CircuitDetail;
