/**
 * 机柜管理页面
 * - 列表查询、新增、编辑、删除
 * - 机房筛选（支持 URL 参数 roomId 自动筛选）
 * - 跳转查看该机柜下的设备
 */
import { useEffect } from 'react';
import { Button, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import DataTable from '@/components/DataTable';
import IdCell from '@/components/IdCell';
import FilterBar from '@/components/FilterBar';
import CabinetForm from './CabinetForm';
import { useCabinetList, useDeleteCabinet, type CabinetQueryParams } from '@/services/cabinet';
import { useRoomOptions } from '@/services/room';
import { CABINET_STATUS_MAP } from '@/types/enums';
import type { Cabinet } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { formatDateTime, formatPercent } from '@/utils/format';


function Cabinets() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: roomOptions } = useRoomOptions();

  const crud = useCrudPage<Cabinet, CabinetQueryParams>({
    useList: useCabinetList,
    useDelete: useDeleteCabinet,
    nameKey: 'cabinet_number',
    nameLabel: '机柜',
    
    
    buildListParams: (tp) =>
      ({
        ...tp,
        room_id: tp.filters?.room_id ? Number(tp.filters.room_id) : undefined
      }) as CabinetQueryParams
  });

  
  const initialRoomId = searchParams.get('roomId');

  
  useEffect(() => {
    const roomId = searchParams.get('roomId');
    if (roomId) {
      crud.table.updateFilter('room_id', Number(roomId));
    }
  }, [searchParams]);

  
  const handleDetail = (record: Cabinet) => {
    navigate(`/cabinets/${record.id}`);
  };

  
  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    { title: '机柜编号', dataIndex: 'cabinet_number', key: 'cabinet_number', width: 120 },
    { title: '所属机房', dataIndex: 'room_name', key: 'room_name', width: 120 },
    {
      title: '位置',
      key: 'position',
      width: 100,
      render: (_: unknown, record: Cabinet) => {
        if (record.row != null && record.col != null) {
          return `行${record.row} 列${record.col}`;
        }
        return record.location ?? '-';
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (v: number) => {
        const s = CABINET_STATUS_MAP[v as keyof typeof CABINET_STATUS_MAP];
        return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
      }
    },
    { title: 'U位容量', dataIndex: 'total_u', key: 'total_u', width: 80 },
    {
      title: '已用U位',
      key: 'used_u',
      width: 120,
      render: (_: unknown, record: Cabinet) => (
        <span>
          {record.used_u}/{record.total_u} ({formatPercent(record.used_u / record.total_u)})
        </span>
      )
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) => v ?? '-'
    },
    { title: '设备数', dataIndex: 'device_count', key: 'device_count', width: 80 },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Cabinet) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/devices?cabinetId=${record.id}`)}
          >
            查看设备
          </Button>
          <Button type="link" size="small" onClick={() => handleDetail(record)}>
            详情
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

  return (
    <div>
      <DataTable<Cabinet>
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
        toolbar={
          <FilterBar
            filters={[
              {
                key: 'room_id',
                label: '按机房筛选',
                type: 'select',
                options: roomOptions ?? [],
                width: 200
              }
            ]}
            table={crud.table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={crud.handleAdd}>
                新增机柜
              </Button>
            }
          />
        }
      />
      <CabinetForm open={crud.formOpen} editRecord={crud.editRecord} onClose={crud.closeForm} />
    </div>
  );
}

export default Cabinets;
