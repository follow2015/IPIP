/**
 * 机柜管理页面
 * - 列表查询、新增、编辑、删除
 * - 机房筛选（支持 URL 参数 roomId 自动筛选）
 * - 跳转查看该机柜下的设备
 */
import { useEffect } from 'react';
import { Button, Space, Tag, Typography } from 'antd';
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

  const renderCabinetCard = (r: Cabinet) => {
    const { Text } = Typography;
    const s = getCabinetStatusMeta(r.status, td);
    const pos =
      r.row != null && r.col != null
        ? td('cabinet.field.rowCol', { row: r.row, col: r.col })
        : (r.location ?? '-');
    const uText =
      r.total_u != null && r.total_u > 0
        ? `${r.used_u ?? 0}/${r.total_u} (${formatPercent((r.used_u ?? 0) / r.total_u)})`
        : '-';
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
        <Space wrap size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => handleDetail(r)}>
            <Text strong>{r.cabinet_number ?? '-'}</Text>
          </Button>
          {s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{r.status}</Tag>}
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.room_name || '-'}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {pos}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {td('cabinet.field.usedU')}: {uText}
        </Text>
        {r.customer_name ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {tc('field.customer')}: {r.customer_name}
          </Text>
        ) : null}
        <Text type="secondary" style={{ fontSize: 12 }}>
          {td('cabinet.field.deviceCount')}: {r.device_count ?? 0}
        </Text>
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            style={{ padding: 0 }}
            onClick={() => navigate(`/devices?cabinetId=${r.id}`)}
          >
            {td('cabinet.viewDevices')}
          </Button>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => handleDetail(r)}>
            {tc('action.detail')}
          </Button>
          <Button
            type="link"
            size="small"
            style={{ padding: 0 }}
            onClick={() => crud.handleEdit(r)}
          >
            {tc('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            style={{ padding: 0 }}
            onClick={() => crud.handleDelete(r)}
          >
            {tc('action.delete')}
          </Button>
        </Space>
      </div>
    );
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
    {
      title: td('cabinet.field.deviceCount'),
      dataIndex: 'device_count',
      key: 'device_count',
      width: 80
    },
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
        error={crud.error}
        onRetry={crud.refetch}
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
        mobileCardMode
        cardRender={renderCabinetCard}
      />
      <CabinetForm open={crud.formOpen} editRecord={crud.editRecord} onClose={crud.closeForm} />
    </div>
  );
}

export default Cabinets;
