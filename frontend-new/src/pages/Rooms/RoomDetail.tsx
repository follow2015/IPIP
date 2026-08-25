/**
 * 机房详情页
 * - 机房基本信息
 * - 机房平面图（RoomLayout 组件）
 * - 机柜统计概览
 */
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Spin, Button, Tag, Row, Col, Statistic, Result } from 'antd';
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  AppstoreOutlined
} from '@ant-design/icons';
import { useRoomSuspenseDetail, useRoomCabinets } from '@/services/room';
import RoomLayout from '@/components/RoomLayout';
import { ROOM_STATUS_MAP } from '@/types/enums';
import { formatDateTime } from '@/utils/format';
import type { Cabinet } from '@/types/models';


function renderStatus(v: number) {
  const s = ROOM_STATUS_MAP[v as keyof typeof ROOM_STATUS_MAP];
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}


function RoomDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const roomId = Number(id);

  if (Number.isNaN(roomId)) {
    return (
      <Result
        status="404"
        title="参数无效"
        subTitle="机房 ID 无效"
        extra={<Button onClick={() => navigate(-1)}>返回</Button>}
      />
    );
  }

  return <RoomDetailContent roomId={roomId} />;
}


function RoomDetailContent({ roomId }: { roomId: number }) {
  const navigate = useNavigate();
  const { data: room } = useRoomSuspenseDetail(roomId);
  const { data: cabinets, isLoading: cabinetsLoading } = useRoomCabinets(roomId);

  if (!room) {
    return <div>机房不存在</div>;
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
          返回列表
        </Button>
        <Button type="primary" onClick={() => navigate(`/cabinets?roomId=${roomId}`)}>
          查看机柜列表
        </Button>
      </div>

      <Card title={`机房详情 - ${room.name}`}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="机房名称">{room.name}</Descriptions.Item>
          <Descriptions.Item label="状态">{renderStatus(room.status)}</Descriptions.Item>
          <Descriptions.Item label="位置">{room.location || '-'}</Descriptions.Item>
          <Descriptions.Item label="机柜数">{totalCabinets}</Descriptions.Item>
          <Descriptions.Item label="联系人">{room.contact || '-'}</Descriptions.Item>
          <Descriptions.Item label="联系电话">{room.contact_phone || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDateTime(room.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDateTime(room.updated_at)}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="统计概览" style={{ marginTop: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="机柜总数" value={totalCabinets} prefix={<DatabaseOutlined />} />
          </Col>
          <Col span={6}>
            <Statistic title="设备总数" value={totalDevices} prefix={<AppstoreOutlined />} />
          </Col>
          <Col span={6}>
            <Statistic
              title="平均U位利用率"
              value={avgUUsage}
              suffix="%"
              prefix={<ThunderboltOutlined />}
              styles={{ content: { color: avgUUsage > 80 ? '#cf1322' : '#3f8600' } }}
            />
          </Col>
          <Col span={6}>
            <Statistic title="已定位机柜" value={positionedCount} suffix={`/ ${totalCabinets}`} />
          </Col>
        </Row>
      </Card>

      <Card title="机房平面图" style={{ marginTop: 16 }}>
        <Spin spinning={cabinetsLoading}>
          <RoomLayout cabinets={cabinetList} />
        </Spin>
      </Card>
    </div>
  );
}

export default RoomDetail;
