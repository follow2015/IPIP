/**
 * 链路聚合组管理页面
 * - 全局视图：按机房筛选，后端分页
 * - 点击交换机名称跳转到设备详情页链路聚合标签（#lag hash）
 * - 管理型交换机（has_ssh=true）仅展示，屏蔽删除
 * - 非网管型交换机（has_ssh=false）支持删除
 * - 新建时交换机列表只显示非管理型
 * - 默认加载第一个机房，防止全量加载
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Tag, Popconfirm, Table, Card } from 'antd';
import { StatusTag } from '@/components/StatusTag';
import { LAG_STATUS_MAP } from '@/types/enums';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useAllLinkAggregationGroups,
  useDeleteLinkAggregationGroup,
  type LinkAggregationGroupWithDevice
} from '@/services/link-aggregation';
import { useRoomOptions } from '@/services/room';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import FilterBar from '@/components/FilterBar';
import { formatDateTime } from '@/utils/format';
import LAGForm from './LAGForm';

function LinkAggregations() {
  const navigate = useNavigate();
  const message = useMessage();
  const table = useTable();
  const { data: roomOptions } = useRoomOptions();

  
  useEffect(() => {
    if (!table.filters.room_id && roomOptions && roomOptions.length > 0) {
      table.updateFilter('room_id', roomOptions[0].value as number);
    }
  }, [roomOptions, table.filters.room_id]);

  
  const {
    data: lagData,
    isLoading,
    refetch
  } = useAllLinkAggregationGroups({
    page: table.page,
    per_page: table.perPage,
    search: table.search || undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
  });

  
  const [createModalOpen, setCreateModalOpen] = useState(false);

  
  const deleteLag = useDeleteLinkAggregationGroup();
  const handleDelete = useCallback(
    async (record: LinkAggregationGroupWithDevice) => {
      try {
        await deleteLag.mutateAsync({ deviceId: record.device_id, lagId: record.id });
        message.success('已删除');
        refetch();
      } catch (err) {
        message.error(err instanceof Error ? err.message : '删除失败');
      }
    },
    [deleteLag, message, refetch]
  );

  
  const goToLagTab = useCallback(
    (deviceId: number) => {
      navigate(`/devices/${deviceId}#lag`);
    },
    [navigate]
  );

  
  const columns = useMemo(
    () => [
      {
        title: '交换机',
        dataIndex: 'device_name',
        key: 'device_name',
        width: 180,
        render: (v: string, record: LinkAggregationGroupWithDevice) => (
          <Button
            type="link"
            size="small"
            style={{ padding: 0 }}
            onClick={() => goToLagTab(record.device_id)}
          >
            {v}
          </Button>
        )
      },
      { title: '聚合组名称', dataIndex: 'lag_name', key: 'lag_name', width: 140 },
      {
        title: '类型',
        dataIndex: 'lag_type',
        key: 'lag_type',
        width: 100,
        render: (v: string) => (
          <Tag color={v === 'lacp' ? 'blue' : 'default'}>{v === 'lacp' ? 'LACP' : '静态'}</Tag>
        )
      },
      {
        title: '负载算法',
        dataIndex: 'algorithm',
        key: 'algorithm',
        width: 120,
        render: (v: string | null) => v || '-'
      },
      {
        title: '用途',
        dataIndex: 'purpose',
        key: 'purpose',
        width: 140,
        render: (v: string | null) => v ?? '-'
      },
      { title: '成员数', dataIndex: 'member_count', key: 'member_count', width: 80 },
      {
        title: '成员端口',
        dataIndex: 'member_ports',
        key: 'member_ports',
        render: (v: string[] | null) => (v?.length ? v.join(', ') : '-')
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (v: number) => <StatusTag status={v} statusMap={LAG_STATUS_MAP} />
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 160,
        render: (v: string) => formatDateTime(v)
      },
      {
        title: '操作',
        key: 'action',
        width: 100,
        render: (_: unknown, record: LinkAggregationGroupWithDevice) => {
          if (record.has_ssh) return <span style={{ color: '#999' }}>网管型</span>;
          return (
            <Popconfirm
              title={`确定要删除「${record.lag_name}」吗？`}
              onConfirm={() => handleDelete(record)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          );
        }
      }
    ],
    [goToLagTab, handleDelete]
  );

  return (
    <div>
      <Card
        title="链路聚合组管理"
        extra={
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
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalOpen(true)}
              >
                新建
              </Button>
            }
          />
        }
      >
        <Table
          columns={columns}
          dataSource={lagData?.items ?? []}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{
            current: table.page,
            pageSize: table.perPage,
            total: lagData?.total ?? 0,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              table.setPage(p);
              table.setPerPage(ps);
            }
          }}
        />
      </Card>

      {}
      <LAGForm
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onSuccess={() => {
          setCreateModalOpen(false);
          refetch();
        }}
      />
    </div>
  );
}

export default LinkAggregations;
