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
import { useAllocatableCustomerOptions } from '@/services/customer';
import { getCabinetStatusMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Cabinet } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { formatDateTime, formatPercent } from '@/utils/format';

function Cabinets() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: roomOptions } = useRoomOptions();
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const crud = useCrudPage<Cabinet, CabinetQueryParams>({
    useList: useCabinetList,
    useDelete: useDeleteCabinet,
    nameKey: 'cabinet_number',
    nameLabel: td('field.cabinet'),
    buildListParams: (tp) =>
      ({
        ...tp,
        room_id: tp.filters?.room_id ? Number(tp.filters.room_id) : undefined,
        customer_id: tp.filters?.customer_id ? Number(tp.filters.customer_id) : undefined
      }) as CabinetQueryParams
  });

  const initialRoomId = searchParams.get('roomId');

  const { filters, updateFilter } = crud.table;

  useEffect(() => {
    const roomId = searchParams.get('roomId');
    if (roomId && filters.room_id !== roomId) {
      updateFilter('room_id', Number(roomId));
    }
  }, [searchParams, filters, updateFilter]);

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
    { title: td('cabinet.number'), dataIndex: 'cabinet_number', key: 'cabinet_number', width: 120 },
    { title: td('basic.field.room'), dataIndex: 'room_name', key: 'room_name', width: 120 },
    {
      title: td('cabinet.field.location'),
      key: 'position',
      width: 100,
      render: (_: unknown, record: Cabinet) => {
        if (record.row != null && record.col != null) {
          return td('cabinet.field.rowCol', { row: record.row, col: record.col });
        }
        return record.location ?? '-';
      }
    },
    {
      title: tc('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (v: number) => {
        const s = getCabinetStatusMeta(v, td);
        return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
      }
    },
    { title: td('cabinet.field.totalU'), dataIndex: 'total_u', key: 'total_u', width: 80 },
    {
      title: td('cabinet.field.usedU'),
      key: 'used_u',
      width: 120,
      render: (_: unknown, record: Cabinet) => (
        <span>
          {record.used_u}/{record.total_u} ({formatPercent(record.used_u / record.total_u)})
        </span>
      )
    },
    {
      title: tc('field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) => v ?? '-'
    },
    { title: td('cabinet.field.deviceCount'), dataIndex: 'device_count', key: 'device_count', width: 80 },
    {
      title: tc('field.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, record: Cabinet) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/devices?cabinetId=${record.id}`)}
          >
            {td('cabinet.viewDevices')}
          </Button>
          <Button type="link" size="small" onClick={() => handleDetail(record)}>
            {tc('action.detail')}
          </Button>
          <Button type="link" size="small" onClick={() => crud.handleEdit(record)}>
            {tc('action.edit')}
          </Button>
          <Button type="link" size="small" danger onClick={() => crud.handleDelete(record)}>
            {tc('action.delete')}
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
                label: td('filter.byRoom'),
                type: 'select',
                options: roomOptions ?? [],
                width: 200
              },
              {
                key: 'customer_id',
                label: td('filter.byCustomer'),
                type: 'select',
                options: customerOptions ?? [],
                width: 200
              }
            ]}
            table={crud.table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={crud.handleAdd}>
                {td('cabinet.add')}
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
