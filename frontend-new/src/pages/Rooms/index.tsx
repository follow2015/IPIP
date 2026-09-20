import { useNavigate } from 'react-router-dom';
import { Button, Tag, Space } from 'antd';
import { PlusOutlined, AppstoreOutlined } from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import IdCell from '@/components/IdCell';
import RoomForm from './RoomForm';
import { useRoomList, useDeleteRoom, useRoomBuildings, useRoomFloors } from '@/services/room';
import { ROOM_STATUS_MAP } from '@/types/enums';
import type { Room } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { formatDateTime } from '@/utils/format';
import type { PaginationParams } from '@/types/api';

type RoomListParams = PaginationParams & {
  search?: string;
  building?: string;
  floor?: string;
  status?: number;
};

function Rooms() {
  const navigate = useNavigate();
  const crud = useCrudPage<Room, RoomListParams>({
    useList: useRoomList,
    useDelete: useDeleteRoom,
    nameKey: 'name',
    nameLabel: '机房',
    buildListParams: (tp) => ({
      page: tp.page,
      per_page: tp.per_page,
      search: tp.search,
      building: typeof tp.filters?.building === 'string' ? tp.filters.building : undefined,
      floor: typeof tp.filters?.floor === 'string' ? tp.filters.floor : undefined,
      status: tp.filters?.status ? Number(tp.filters.status) : undefined
    })
  });

  const { data: buildingOptions } = useRoomBuildings();
  const buildingFilterValue =
    typeof crud.table.filters.building === 'string' ? crud.table.filters.building : undefined;
  const { data: floorOptions } = useRoomFloors(buildingFilterValue);

  const handleDetail = (record: Room) => {
    navigate(`/rooms/${record.id}`);
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    { title: '机房名称', dataIndex: 'name', key: 'name' },
    {
      title: '房间号',
      dataIndex: 'room_number',
      key: 'room_number',
      width: 110
    },
    {
      title: '楼栋',
      dataIndex: 'building',
      key: 'building',
      width: 120,
      render: (v: string | null) => v || '-'
    },
    {
      title: '楼层',
      dataIndex: 'floor',
      key: 'floor',
      width: 90,
      render: (v: string | null) => v || '-'
    },
    { title: '位置', dataIndex: 'location', key: 'location' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => {
        const s = ROOM_STATUS_MAP[v as keyof typeof ROOM_STATUS_MAP];
        return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
      }
    },
    { title: '机柜数', dataIndex: 'cabinet_count', key: 'cabinet_count', width: 80 },
    {
      title: '联系人',
      dataIndex: 'contact',
      key: 'contact',
      render: (v: string | null) => v || '-'
    },
    {
      title: '联系电话',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      render: (v: string | null) => v || '-'
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => formatDateTime(v)
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Room) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleDetail(record)}>
            平面图
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/cabinets?roomId=${record.id}`)}
          >
            查看机柜
          </Button>
          <Button type="link" size="small" onClick={() => crud.handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger onClick={() => crud.handleDelete(record)}>
            删除
          </Button>
        </Space>
      )
    }
  ];

  const filterBar = (
    <FilterBar
      table={crud.table}
      filters={[
        {
          key: 'building',
          label: '全部楼栋',
          type: 'select',
          width: 150,
          showSearch: true,
          options: (buildingOptions ?? []).map((b) => ({ label: b, value: b }))
        },
        {
          key: 'floor',
          label: buildingFilterValue ? '全部楼层' : '楼层（先选楼栋）',
          type: 'select',
          width: 150,
          showSearch: true,
          options: (floorOptions ?? []).map((f) => ({ label: f, value: f }))
        },
        {
          key: 'status',
          label: '全部状态',
          type: 'select',
          width: 120,
          options: Object.entries(ROOM_STATUS_MAP).map(([value, s]) => ({
            label: s.label,
            value: Number(value)
          }))
        }
      ]}
      extra={
        <Space>
          <Button icon={<AppstoreOutlined />} onClick={() => navigate('/rooms/overview')}>
            机房总览
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={crud.handleAdd}>
            新增机房
          </Button>
        </Space>
      }
    />
  );

  return (
    <div>
      <DataTable<Room>
        columns={columns}
        dataSource={crud.data?.items ?? []}
        loading={crud.isLoading}
        rowKey="id"
        total={crud.data?.total}
        page={crud.table.page}
        perPage={crud.table.perPage}
        onPageChange={(p, ps) => {
          crud.table.setPage(p);
          if (ps !== crud.table.perPage) crud.table.setPerPage(ps);
        }}
        searchValue={crud.table.search}
        onSearch={crud.table.setSearch}
        onRefresh={() => crud.refetch()}
        toolbar={filterBar}
      />
      <RoomForm open={crud.formOpen} editRecord={crud.editRecord} onClose={crud.closeForm} />
    </div>
  );
}

export default Rooms;
