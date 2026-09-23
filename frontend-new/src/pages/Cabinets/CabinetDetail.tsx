
import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Spin, Button, Tag, Result, Space } from 'antd';
import { ArrowLeftOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useCabinetSuspenseDetail, useCabinetWithDevices } from '@/services/cabinet';
import { useRoomChannels } from '@/services/room';
import { useUpdateDevice } from '@/services/device';
import { useVendorBrands } from '@/services/monitor';
import { queryKeys } from '@/services/query-keys';
import UPositionSelector from '@/components/UPositionSelector';
import {
  CHANNEL_TYPE_LABEL_KEYS,
  paletteKeyOf,
  positionLabel
} from '@/components/RoomLayout/palette';
import type {
  OccupiedPosition,
  RackDeviceType,
  DeviceNode,
  NodeStatus
} from '@/components/UPositionSelector/UPositionSelector';
import { formatDateTime } from '@/utils/format';
import { useMessage } from '@/hooks/useMessage';
import { DeviceStatusCode } from '@/types/enums';
import type { Cabinet, Device, RoomChannel } from '@/types/models';
import { getCabinetStatusMeta, type DeviceT } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

function renderStatus(v: number, t: DeviceT) {
  const s = getCabinetStatusMeta(v, t);
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}

function ChannelTag({ channel, side }: { channel: RoomChannel; side: 'left' | 'right' }) {
  const { t: ta } = useTranslation('asset');
  const typeKey = CHANNEL_TYPE_LABEL_KEYS[channel.channel_type];
  const typeLabel = typeKey ? ta(typeKey) : channel.channel_type;
  return (
    <Tag color={paletteKeyOf(channel.channel_type)}>
      {side === 'left' ? ta('roomLayout.channel.sideLeft') : ta('roomLayout.channel.sideRight')}
      {typeLabel}
      {channel.enclosed
        ? ta('roomLayout.channel.enclosedDot')
        : ta('roomLayout.channel.openDot')}
    </Tag>
  );
}

function CabinetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const cabinetId = Number(id);

  if (Number.isNaN(cabinetId)) {
    return (
      <Result
        status="404"
        title={td('detail.invalidParam')}
        subTitle={td('cabinet.invalidId')}
        extra={<Button onClick={() => navigate(-1)}>{tc('action.back')}</Button>}
      />
    );
  }

  return <CabinetDetailContent cabinetId={cabinetId} />;
}

function CabinetDetailContent({ cabinetId }: { cabinetId: number }) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { t: ta } = useTranslation('asset');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (cabinetId > 0) {
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.withDevices(cabinetId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.detail(cabinetId) });
    }
  }, [cabinetId, queryClient]);

  const { data: cabinet } = useCabinetSuspenseDetail(cabinetId);
  const { data: cabinetWithDevices } = useCabinetWithDevices(cabinetId);
  const { data: channels } = useRoomChannels(cabinet?.room_id ?? 0);
  const updateDevice = useUpdateDevice();
  const { data: vendorBrands } = useVendorBrands();
  const message = useMessage();

  const vendorLabelMap = new Map<string, string>();
  for (const v of vendorBrands?.items ?? []) {
    if (!vendorLabelMap.has(v.enterprise_no)) vendorLabelMap.set(v.enterprise_no, v.label);
  }

  const handlePositionChange = useCallback(
    (deviceId: number, newUPos: number) => {
      updateDevice.mutate(
        { id: deviceId, u_position: newUPos } as Parameters<typeof updateDevice.mutate>[0],
        {
          onSuccess: () => {
            message.success(td('cabinet.message.uPositionUpdated'));
            queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.detail(cabinetId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.withDevices(cabinetId) });
          },
          onError: () => message.error(td('cabinet.message.uPositionUpdateFailed'))
        }
      );
    },
    [updateDevice, cabinetId, queryClient, td]
  );

  if (!cabinet) {
    return <div>{td('cabinet.notFound')}</div>;
  }

  function mapDeviceType(d: Device): RackDeviceType {
    if (d.is_chassis) return 'multinode';
    const sub = d.device_subtype;
    if (sub === 'switch' || sub === 'router' || sub === 'firewall') return 'switch';
    if (sub === 'pdu') return 'pdu';
    if (sub === 'ups') return 'kvm';
    const main = d.device_type;
    if (main === 'network') return 'switch';
    return 'server';
  }

  function mapNodeStatus(status: number): NodeStatus {
    if (status === DeviceStatusCode.ONLINE) return 'active'; // 在线
    if (status === DeviceStatusCode.OFFLINE) return 'inactive'; // 离线
    if (status === DeviceStatusCode.MAINTENANCE) return 'fault'; // 故障/维护
    return 'inactive';
  }

  const allDevices = ((cabinetWithDevices as { devices?: Device[] })?.devices ?? []) as Device[];

  const topDevices = allDevices.filter((d) => !d.parent_device_id);

  const occupiedPositions: OccupiedPosition[] = topDevices.map((d) => {
    let nodes: DeviceNode[] | undefined;
    if (d.is_chassis) {
      const childDevices = allDevices.filter((c) => c.parent_device_id === d.id);
      if (childDevices.length > 0) {
        nodes = childDevices.map((child) => ({
          id: String(child.id),
          label: child.device_name,
          status: mapNodeStatus(child.status),
          ip: child.management_ip || child.ip_address || undefined,
          ipmiAddress: (child as Device & { ipmi_address?: string }).ipmi_address || undefined,
          row: child.node_row ?? undefined,
          col: child.node_col ?? undefined
        }));
      }
    }

    return {
      uPosition: d.u_position ?? 0,
      uSize: d.height_u || 1,
      deviceName: d.device_name,
      deviceId: d.id,
      deviceType: mapDeviceType(d),
      power: d.power ?? undefined,
      ip: d.management_ip || d.ip_address || undefined,
      ipmiAddress: (d as Device & { ipmi_address?: string }).ipmi_address || undefined,
      sn: d.serial_number || undefined,
      vendor: (d.brand && vendorLabelMap.get(d.brand)) || undefined,
      model: d.device_model || undefined,
      nodes,
      nodeRows: d.is_chassis ? (d.node_rows ?? undefined) : undefined,
      nodeCols: d.is_chassis ? (d.node_cols ?? undefined) : undefined
    };
  });

  const c = cabinet as Cabinet;

  const hasPosition = c.row != null && c.col != null && c.row > 0 && c.col > 0;

  const leftChannel = hasPosition
    ? (channels ?? []).find((ch) => ch.col_number === c.col! - 1)
    : undefined;
  const rightChannel = hasPosition
    ? (channels ?? []).find((ch) => ch.col_number === c.col!)
    : undefined;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/cabinets')}>
          {td('detail.backToList')}
        </Button>
        <Button type="primary" onClick={() => navigate(`/devices?cabinetId=${cabinetId}`)}>
          {td('cabinet.viewDevices')}
        </Button>
      </div>

      <Card title={td('cabinet.detailTitle', { number: c.cabinet_number })}>
        <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
          <Descriptions.Item label={td('cabinet.number')}>{c.cabinet_number}</Descriptions.Item>
          <Descriptions.Item label={tc('field.status')}>{renderStatus(c.status, td)}</Descriptions.Item>
          <Descriptions.Item label={td('basic.field.room')}>{c.room_name}</Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.roomLocation')}>
            {c.room_location ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.exactLocation')}>
            {c.location ?? '-'}
          </Descriptions.Item>
          {/*
            平面图位置（设计文档 §3.4）：此前 row/col 填了却完全不展示，运维想知道
            机柜在第几行第几列只能跳回平面图自己找；加了通道后这个缺口更明显
            （冷/热通道信息理应跟着位置一起露出）。
          */}
          <Descriptions.Item label={ta('roomLayout.planPosition')}>
            {hasPosition ? (
              <Space size={4} wrap>
                <span>{positionLabel(c.row ?? 0, c.col ?? 0, ta)}</span>
                {leftChannel ? <ChannelTag channel={leftChannel} side="left" /> : null}
                {rightChannel ? <ChannelTag channel={rightChannel} side="right" /> : null}
                {!leftChannel && !rightChannel ? (
                  <span style={{ color: '#8c8c8c' }}>{ta('roomLayout.channel.unmarked')}</span>
                ) : null}
                <Button
                  type="link"
                  size="small"
                  icon={<EnvironmentOutlined />}
                  onClick={() => navigate(`/rooms/${c.room_id}?cabinetId=${c.id}`)}
                >
                  {ta('roomLayout.viewOnPlan')}
                </Button>
              </Space>
            ) : (
              <span style={{ color: '#8c8c8c' }}>{ta('roomLayout.positionNotSet')}</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.leaseCustomer')}>
            {c.customer_name ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.totalU')}>{c.total_u}U</Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.usedU')}>
            <Tag color={c.used_u > c.total_u * 0.8 ? 'red' : 'green'}>{c.used_u}U</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.availableU')}>{c.available_u}U</Descriptions.Item>
          <Descriptions.Item label={ta('uposition.side.uUsage')}>{c.u_usage_rate}%</Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.ratedPowerUnit')}>
            {c.total_power ? `${c.total_power}W` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.usedPower')}>
            {c.total_power ? (
              <Tag color={c.power_usage_rate > 80 ? 'red' : 'green'}>{c.used_power}W</Tag>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label={ta('uposition.side.powerUsage')}>
            {c.total_power ? `${c.power_usage_rate}%` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.maxWeight')}>
            {c.max_weight ? `${c.max_weight}KG` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.deviceCount')}>{c.device_count}</Descriptions.Item>
          <Descriptions.Item label={tc('field.createdAt')}>{formatDateTime(c.created_at)}</Descriptions.Item>
          <Descriptions.Item label={tc('field.updatedAt')} span={1}>
            {formatDateTime(c.updated_at)}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.remarks')} span={1}>
            {c.notes || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={ta('uposition.header.title')} style={{ marginTop: 16 }}>
        <UPositionSelector
          totalU={c.total_u}
          ratedPower={c.total_power ?? undefined}
          occupiedPositions={occupiedPositions}
          readOnly={false}
          onPositionChange={handlePositionChange}
          onNodeReorder={(chassisId, newOrderedNodeIds) => {
            console.log('Chassis node reorder:', chassisId, newOrderedNodeIds);
          }}
          onSelect={() => {}}
        />
      </Card>
    </div>
  );
}

export default CabinetDetail;
