/**
 * VLAN 管理页面
 * - 全局视图：按机房筛选，后端分页
 * - 点击交换机名称跳转到设备详情页 VLAN 标签（#vlans hash）
 * - 管理型交换机（has_ssh=true）仅展示，屏蔽删除
 * - 非网管型交换机（has_ssh=false）支持删除
 * - 新增 VLAN 时交换机列表只显示非管理型（见 VLANForm）
 * - 默认加载第一个机房，防止全量加载
 */
import { useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Tooltip } from 'antd';
import { StatusTag } from '@/components/StatusTag';
import { VLAN_STATUS_MAP } from '@/types/enums';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useVLANList, useDeleteVLAN, type VLANQueryParams } from '@/services/vlan';
import { useRoomOptions } from '@/services/room';
import { useSwitchList } from '@/services/switch';
import type { VLAN } from '@/types/models';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import { useCrudPage } from '@/hooks/useCrudPage';
import { formatDateTime } from '@/utils/format';
import VLANForm from './VLANForm';


interface VLANWithHasSsh extends VLAN {
  has_ssh?: boolean;
}


function VLANs() {
  const navigate = useNavigate();
  const { data: roomOptions } = useRoomOptions();
  const { data: switchList } = useSwitchList();

  const crud = useCrudPage<VLANWithHasSsh, VLANQueryParams>({
    useList: useVLANList,
    useDelete: useDeleteVLAN,
    nameKey: 'name',
    nameLabel: 'VLAN',
    
    
    buildListParams: (tp) =>
      ({
        ...tp,
        room_id: tp.filters?.room_id ? Number(tp.filters.room_id) : undefined
      }) as VLANQueryParams
  });
  const { table, data, isLoading, refetch, handleAdd, handleDelete, closeForm, formOpen } = crud;

  
  useEffect(() => {
    if (!table.filters.room_id && roomOptions && roomOptions.length > 0) {
      table.updateFilter('room_id', roomOptions[0].value as number);
    }
  }, [roomOptions, table.filters.room_id]);

  
  const switchNameMap = useMemo(
    () => new Map((switchList?.items ?? []).map((sw: any) => [sw.id, sw.name || sw.ip])),
    [switchList]
  );

  
  const goToVlanTab = useCallback(
    (deviceId: number) => {
      navigate(`/devices/${deviceId}#vlans`);
    },
    [navigate]
  );

  
  const columns = useMemo(
    () => [
      { title: 'VLAN ID', dataIndex: 'vlan_id', key: 'vlan_id', width: 90 },
      { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
      {
        title: '用途',
        dataIndex: 'purpose',
        key: 'purpose',
        width: 140,
        render: (v: string | null) => v ?? '-'
      },
      {
        title: '交换机',
        dataIndex: 'device_id',
        key: 'device_id',
        width: 160,
        render: (v: number | null, record: any) => {
          if (!v) return '-';
          const name = record.device_name || switchNameMap.get(v);
          return (
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => goToVlanTab(v)}>
              {name || `设备 #${v}`}
            </Button>
          );
        }
      },
      {
        title: '机房',
        dataIndex: 'room_id',
        key: 'room_id',
        width: 100,
        render: (v: number | null, record: any) => record.room_name || (v ? `机房 #${v}` : '-')
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (v: number) => <StatusTag status={v} statusMap={VLAN_STATUS_MAP} />
      },
      {
        title: '成员端口',
        dataIndex: 'member_ports',
        key: 'member_ports',
        render: (v: string[] | null) => {
          if (!v || v.length === 0) return '-';
          if (v.length <= 3) return v.join(', ');
          return (
            <Tooltip title={v.join(', ')}>
              <span>
                {v.slice(0, 3).join(', ')}... ({v.length})
              </span>
            </Tooltip>
          );
        }
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 150,
        render: (v: string) => formatDateTime(v)
      },
      {
        title: '操作',
        key: 'action',
        width: 100,
        render: (_: unknown, r: VLANWithHasSsh) => {
          if (r.has_ssh) return <span style={{ color: '#999' }}>网管型</span>;
          return (
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(r)}
            >
              删除
            </Button>
          );
        }
      }
    ],
    [switchNameMap, goToVlanTab, handleDelete]
  );

  return (
    <div>
      <DataTable<VLANWithHasSsh>
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder="搜索 VLAN ID/名称/用途..."
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={() => refetch()}
        total={data?.total ?? 0}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        toolbar={
          <FilterBar
            filters={[
              {
                key: 'room_id',
                label: '按机房筛选',
                type: 'select',
                options: roomOptions ?? [],
                width: 160
              }
            ]}
            table={table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                新增 VLAN
              </Button>
            }
          />
        }
      />

      <VLANForm
        open={formOpen}
        onCancel={closeForm}
        onSuccess={() => {
          closeForm();
          refetch();
        }}
      />
    </div>
  );
}

export default VLANs;
