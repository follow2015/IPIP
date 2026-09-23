import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Card,
  Col,
  Empty,
  Input,
  Progress,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Tooltip,
  Typography,
  theme
} from 'antd';
import { ClusterOutlined, DatabaseOutlined, SearchOutlined } from '@ant-design/icons';
import { useRoomOverview } from '@/services/room';
import { useTranslation } from 'react-i18next';
import { CABINET_STATUS_MAP } from '@/types/enums';
import type { RoomOverviewGroup, RoomOverviewItem } from '@/types/models';
import {
  collectFloors,
  countRooms,
  filterOverviewGroups,
  isFilterEmpty,
  type OverviewFilter
} from './overview-filter';

function usageColor(percent: number, token: ReturnType<typeof theme.useToken>['token']): string {
  if (percent >= 90) return token.colorError;
  if (percent >= 75) return token.colorWarning;
  return token.colorSuccess;
}

function StatusDots({ distribution }: { distribution: RoomOverviewItem['status_distribution'] }) {
  const { t: td } = useTranslation('device');
  const { token } = theme.useToken();
  const entries = useMemo(
    () =>
      Object.entries(distribution ?? {})
        .map(([code, count]) => ({ code: Number(code), count }))
        .filter((e) => e.count > 0)
        .sort((a, b) => a.code - b.code),
    [distribution]
  );

  if (entries.length === 0) return null;

  return (
    <Space size={8} wrap>
      {entries.map(({ code, count }) => {
        const meta = CABINET_STATUS_MAP[code as keyof typeof CABINET_STATUS_MAP];
        return (
          <span
            key={code}
            title={`${meta ? td(meta.labelKey) : code}：${count}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: token[`${meta?.color ?? 'blue'}6` as keyof typeof token] as string
              }}
            />
            <span style={{ color: token.colorTextSecondary }}>
              {meta ? td(meta.labelKey) : code} {count}
            </span>
          </span>
        );
      })}
    </Space>
  );
}

function RoomCard({ room }: { room: RoomOverviewItem }) {
  const { t: td } = useTranslation('device');
  const navigate = useNavigate();
  const { token } = theme.useToken();

  return (
    <Card
      size="small"
      hoverable
      onClick={() => navigate(`/rooms/${room.id}`)}
      style={{ height: '100%' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontWeight: 600 }}>
          {td('room.overview.roomLabel', { number: room.room_number })}
        </span>
        <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
          <DatabaseOutlined /> {room.cabinet_count}
        </span>
      </div>
      <div
        style={{
          fontSize: 12,
          color: token.colorTextTertiary,
          marginBottom: 8,
          minHeight: 20
        }}
      >
        {/* 楼栋/楼层是组内房间卡片的区分维度（组标题已承载机房名称）。
            带"楼栋"/"楼层"前缀而非只显示裸值——楼栋/楼层的值是自由文本
            （可能填 "7"、"7F"、"B1"），单看一个数字无法判断它代表什么。 */}
        {room.building ? (
          <Tag style={{ marginInlineEnd: 4 }}>
            {td('room.overview.buildingTag', { value: room.building })}
          </Tag>
        ) : null}
        {room.floor ? (
          <Tag style={{ marginInlineEnd: 4 }}>
            {td('room.overview.floorTag', { value: room.floor })}
          </Tag>
        ) : null}
        {room.location}
      </div>

      <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
        {td('room.overview.uUsage')}
      </div>
      <Progress
        percent={room.u_usage_rate}
        size="small"
        strokeColor={usageColor(room.u_usage_rate, token)}
      />
      <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
        {td('room.overview.powerUsage')}
      </div>
      <Progress
        percent={room.power_usage_rate}
        size="small"
        strokeColor={usageColor(room.power_usage_rate, token)}
      />

      <div style={{ marginTop: 8 }}>
        <StatusDots distribution={room.status_distribution} />
      </div>
    </Card>
  );
}

function RoomGroup({ group, filtered }: { group: RoomOverviewGroup; filtered: boolean }) {
  const { t: td } = useTranslation('device');
  const { token } = theme.useToken();

  return (
    <div style={{ marginBottom: 24 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 12,
          flexWrap: 'wrap'
        }}
      >
        <Typography.Title level={5} style={{ margin: 0 }}>
          <ClusterOutlined /> {/* 裸值（如 "A"）单看不知含义，故显式标出这是机房 */}
          {td('room.overview.groupRoom', { name: group.name })}
        </Typography.Title>
        <Tag>{td('room.overview.roomCount', { count: group.room_count })}</Tag>
        <Tag>{td('room.overview.cabinetCount', { count: group.cabinet_count })}</Tag>
        {filtered ? (
          <Tooltip title={td('room.overview.utilTooltip')}>
            <span style={{ fontSize: 12, color: token.colorTextTertiary }}>
              {td('room.overview.uAvgDisabled')}
            </span>
          </Tooltip>
        ) : (
          <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
            {td('room.overview.uAvg')} {group.u_usage_rate}%
          </span>
        )}
      </div>
      <Row gutter={[16, 16]}>
        {group.rooms.map((room) => (
          <Col key={room.id} xs={24} sm={12} lg={8} xl={6}>
            <RoomCard room={room} />
          </Col>
        ))}
      </Row>
    </div>
  );
}

function OverviewFilterBar({
  groups,
  filter,
  onChange
}: {
  groups: RoomOverviewGroup[];
  filter: OverviewFilter;
  onChange: (next: OverviewFilter) => void;
}) {
  const { t: td } = useTranslation('device');
  const nameOptions = useMemo(
    () => groups.map((g) => ({ label: g.name ?? '', value: g.name ?? '' })),
    [groups]
  );

  const buildingOptions = useMemo(() => {
    const set = new Set<string>();
    for (const g of groups) {
      for (const r of g.rooms) {
        if (r.building) set.add(r.building);
      }
    }
    return [...set].sort((a, b) => a.localeCompare(b, 'zh')).map((b) => ({ label: b, value: b }));
  }, [groups]);

  const floorOptions = useMemo(
    () => collectFloors(groups).map((f) => ({ label: f, value: f })),
    [groups]
  );

  return (
    <Space wrap style={{ marginBottom: 16 }}>
      <Select
        allowClear
        placeholder={td('room.filter.allRooms')}
        style={{ width: 180 }}
        value={filter.name}
        options={nameOptions}
        onChange={(v?: string) => onChange({ ...filter, name: v })}
      />
      <Select
        allowClear
        placeholder={td('room.filter.allBuildings')}
        style={{ width: 150 }}
        value={filter.building}
        options={buildingOptions}
        onChange={(v?: string) => onChange({ ...filter, building: v })}
      />
      <Select
        allowClear
        placeholder={td('room.filter.allFloors')}
        style={{ width: 130 }}
        value={filter.floor}
        options={floorOptions}
        onChange={(v?: string) => onChange({ ...filter, floor: v })}
      />
      <Input
        allowClear
        placeholder={td('room.filter.searchName')}
        prefix={<SearchOutlined />}
        style={{ width: 180 }}
        value={filter.keyword}
        onChange={(e) => onChange({ ...filter, keyword: e.target.value })}
      />
    </Space>
  );
}

function RoomOverview() {
  const { t: td } = useTranslation('device');
  const { data: groups, isLoading, isError } = useRoomOverview();
  const [filter, setFilter] = useState<OverviewFilter>({});

  const filtered = useMemo(() => filterOverviewGroups(groups ?? [], filter), [groups, filter]);
  const filtering = !isFilterEmpty(filter);

  if (isLoading) {
    return <Skeleton active paragraph={{ rows: 6 }} />;
  }

  if (isError) {
    return <Alert type="error" showIcon message={td('room.overview.loadFailed')} />;
  }

  if (!groups || groups.length === 0) {
    return <Empty description={td('room.overview.empty')} />;
  }

  return (
    <div>
      <OverviewFilterBar groups={groups} filter={filter} onChange={setFilter} />

      {filtered.length === 0 ? (
        <Empty
          description={
            <span>
              {td('room.overview.noneMatched', {
                count: countRooms(groups),
                filtered: filtering ? td('room.overview.filtered') : ''
              })}
            </span>
          }
        >
          <Typography.Link onClick={() => setFilter({})}>
            {td('room.overview.clearFilter')}
          </Typography.Link>
        </Empty>
      ) : (
        filtered.map((group) => <RoomGroup key={group.name} group={group} filtered={filtering} />)
      )}
    </div>
  );
}

export default RoomOverview;
