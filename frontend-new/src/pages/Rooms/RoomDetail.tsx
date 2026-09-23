/**
 * 机房详情页
 * - 机房基本信息
 * - 机房平面图（RoomLayout 组件）
 * - 机柜统计概览
 */
import { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Card, Descriptions, Spin, Button, Tag, Row, Col, Statistic, Result, Space } from 'antd';
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  SettingOutlined,
  AppstoreAddOutlined
} from '@ant-design/icons';
import {
  useRoomSuspenseDetail,
  useRoomCabinets,
  useRoomChannels,
  useRoomLayoutMarkers
} from '@/services/room';
import RoomLayout from '@/components/RoomLayout';
import ChannelConfigModal from '@/components/RoomLayout/ChannelConfigModal';
import MarkerConfigModal from '@/components/RoomLayout/MarkerConfigModal';
import { usePermission } from '@/hooks/usePermission';
import { getRoomStatusMeta, type DeviceT } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';
import type { Cabinet } from '@/types/models';

function renderStatus(v: number, t: DeviceT) {
  const s = getRoomStatusMeta(v, t);
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}

function RoomDetail() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const roomId = Number(id);

  if (Number.isNaN(roomId)) {
    return (
      <Result
        status="404"
        title={td('detail.invalidParam')}
        subTitle={td('room.invalidId')}
        extra={<Button onClick={() => navigate(-1)}>{tc('action.back')}</Button>}
      />
    );
  }

  return <RoomDetailContent roomId={roomId} />;
}

function RoomDetailContent({ roomId }: { roomId: number }) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { t: tm } = useTranslation('monitor');
  const { t: ta } = useTranslation('asset');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const highlightCabinetId = Number(searchParams.get('cabinetId')) || undefined;
  const { data: room } = useRoomSuspenseDetail(roomId);
  const { data: cabinets, isLoading: cabinetsLoading } = useRoomCabinets(roomId);
  const { data: channels } = useRoomChannels(roomId);
  const { data: markers } = useRoomLayoutMarkers(roomId);

  const { hasPermission } = usePermission();
  const canConfigLayout = hasPermission('room:layout_config');
  const [channelModalOpen, setChannelModalOpen] = useState(false);
  const [markerModalOpen, setMarkerModalOpen] = useState(false);

  if (!room) {
    return <div>{td('room.notFound')}</div>;
  }

  const cabinetList = (cabinets ?? []) as Cabinet[];
  const totalCabinets = cabinetList.length;
  const totalDevices = cabinetList.reduce((sum, c) => sum + (c.device_count ?? 0), 0);
  const avgUUsage =
    totalCabinets > 0
      ? Math.round(cabinetList.reduce((sum, c) => sum + (c.u_usage_rate ?? 0), 0) / totalCabinets)
      : 0;
  const positionedCount = cabinetList.filter((c) => c.row != null && c.col != null).length;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/rooms')}>
          {td('detail.backToList')}
        </Button>
        <Button type="primary" onClick={() => navigate(`/cabinets?roomId=${roomId}`)}>
          {td('room.action.viewCabinetList')}
        </Button>
      </div>

      <Card title={td('room.detailTitle', { name: room.name })}>
        <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
          <Descriptions.Item label={td('room.field.name')}>{room.name}</Descriptions.Item>
          <Descriptions.Item label={td('room.field.roomNumber')}>
            {room.room_number || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.status')}>
            {renderStatus(room.status, td)}
          </Descriptions.Item>
          <Descriptions.Item label={td('room.field.building')}>
            {room.building || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('room.field.floor')}>{room.floor || '-'}</Descriptions.Item>
          <Descriptions.Item label={td('cabinet.field.location')}>
            {room.location || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.stats.cabinetCount')}>
            {totalCabinets}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.contactPerson')}>
            {room.contact || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.contactPhone')}>
            {room.contact_phone || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.createdAt')}>
            {formatDateTime(room.created_at)}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.updatedAt')}>
            {formatDateTime(room.updated_at)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={td('room.stats.title')} style={{ marginTop: 16 }}>
        <Row gutter={16}>
          <Col xs={12} md={6}>
            <Statistic
              title={tm('dashboard.metric.cabinetTotal')}
              value={totalCabinets}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={tm('chart.deviceTotal')}
              value={totalDevices}
              prefix={<AppstoreOutlined />}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={td('room.stats.avgUUsage')}
              value={avgUUsage}
              suffix="%"
              prefix={<ThunderboltOutlined />}
              styles={{ content: { color: avgUUsage > 80 ? '#cf1322' : '#3f8600' } }}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={td('room.stats.positionedCabinets')}
              value={positionedCount}
              suffix={`/ ${totalCabinets}`}
            />
          </Col>
        </Row>
      </Card>

      <Card
        title={td('room.floorPlanTitle')}
        style={{ marginTop: 16 }}
        extra={
          canConfigLayout ? (
            <Space>
              <Button icon={<SettingOutlined />} onClick={() => setChannelModalOpen(true)}>
                {ta('roomLayout.channel.title')}
              </Button>
              <Button icon={<AppstoreAddOutlined />} onClick={() => setMarkerModalOpen(true)}>
                {ta('roomLayout.marker.title')}
              </Button>
            </Space>
          ) : null
        }
      >
        <Spin spinning={cabinetsLoading}>
          <RoomLayout
            cabinets={cabinetList}
            channels={channels}
            markers={markers}
            highlightCabinetIds={highlightCabinetId ? [highlightCabinetId] : undefined}
          />
        </Spin>
      </Card>

      {canConfigLayout ? (
        <>
          <ChannelConfigModal
            roomId={roomId}
            open={channelModalOpen}
            onClose={() => setChannelModalOpen(false)}
          />
          <MarkerConfigModal
            roomId={roomId}
            open={markerModalOpen}
            onClose={() => setMarkerModalOpen(false)}
          />
        </>
      ) : null}
    </div>
  );
}

export default RoomDetail;
