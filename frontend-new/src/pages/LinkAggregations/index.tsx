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
import { useDisclosure } from '@/hooks/useDisclosure';
import { useNavigate } from 'react-router-dom';
import { useConfirm } from '@/utils/confirm';
import { Button, Tag, Card } from 'antd';
import DataTable from '@/components/DataTable';
import { serverPagination } from '@/components/DataTable/serverPagination';
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
import { useTranslation } from 'react-i18next';
import LAGForm from './LAGForm';

function LinkAggregations() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const navigate = useNavigate();
  const message = useMessage();
  const table = useTable();
  const { filters, updateFilter } = table;
  const { data: roomOptions } = useRoomOptions();

  useEffect(() => {
    if (!filters.room_id && roomOptions && roomOptions.length > 0) {
      updateFilter('room_id', roomOptions[0].value as number);
    }
  }, [roomOptions, filters, updateFilter]);

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

  const createModal = useDisclosure();

  const deleteLag = useDeleteLinkAggregationGroup();
  const handleDelete = useCallback(
    async (record: LinkAggregationGroupWithDevice) => {
      try {
        await deleteLag.mutateAsync({ deviceId: record.device_id, lagId: record.id });
        message.success(tc('message.deleteSuccess'));
        refetch();
      } catch (err) {
        message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
      }
    },
    [deleteLag, message, refetch, tc]
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
        title: td('deviceSubtype.SWITCH'),
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
      { title: td('lag.column.lagName'), dataIndex: 'lag_name', key: 'lag_name', width: 140 },
      {
        title: tc('field.type'),
        dataIndex: 'lag_type',
        key: 'lag_type',
        width: 100,
        render: (v: string) => (
          <Tag color={v === 'lacp' ? 'blue' : 'default'}>
            {v === 'lacp' ? td('lag.type.lacp') : td('lag.type.static')}
          </Tag>
        )
      },
      {
        title: td('lag.column.algorithm'),
        dataIndex: 'algorithm',
        key: 'algorithm',
        width: 120,
        render: (v: string | null) => v || '-'
      },
      {
        title: tc('field.purpose'),
        dataIndex: 'purpose',
        key: 'purpose',
        width: 140,
        render: (v: string | null) => v ?? '-'
      },
      { title: td('lag.column.memberCount'), dataIndex: 'member_count', key: 'member_count', width: 80 },
      {
        title: td('memberPort.column'),
        dataIndex: 'member_ports',
        key: 'member_ports',
        render: (v: string[] | null) => (v?.length ? v.join(', ') : '-')
      },
      {
        title: tc('field.status'),
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (v: number) => <StatusTag status={v} statusMap={LAG_STATUS_MAP} />
      },
      {
        title: tc('field.updatedAt'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 160,
        render: (v: string) => formatDateTime(v)
      },
      {
        title: tc('field.actions'),
        key: 'action',
        width: 100,
        render: (_: unknown, record: LinkAggregationGroupWithDevice) => {
          if (record.has_ssh) return <span style={{ color: '#999' }}>{td('lag.managed')}</span>;
          return (
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() =>
                confirm({
                  title: td('lag.confirmDeleteContent', { name: record.lag_name }),
                  okText: tc('action.delete'),
                  okButtonProps: { danger: true },
                  onOk: () => handleDelete(record)
                })
              }
            >
              {tc('action.delete')}
            </Button>
          );
        }
      }
    ],
    [confirm, goToLagTab, handleDelete, td, tc]
  );

  return (
    <div>
      <Card
        title={td('lag.pageTitle')}
        extra={
          <FilterBar
            filters={[
              {
                key: 'room_id',
                label: td('filter.byRoom'),
                type: 'select',
                options: roomOptions ?? [],
                width: 160
              }
            ]}
            table={table}
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={() => createModal.open()}>
                {tc('action.create')}
              </Button>
            }
          />
        }
      >
        <DataTable
          columns={columns}
          dataSource={lagData?.items ?? []}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={serverPagination({
            current: table.page,
            pageSize: table.perPage,
            total: lagData?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => tc('pagination.total', { count: total }),
            onChange: (p, ps) => {
              table.setPage(p);
              table.setPerPage(ps);
            }
          })}
          scroll={{ x: 'max-content' }}
          showCard={false}
          searchable={false}
        />
      </Card>

      {/* 创建链路聚合组弹窗 */}
      <LAGForm
        open={createModal.isOpen}
        onCancel={() => createModal.close()}
        onSuccess={() => {
          createModal.close();
          refetch();
        }}
      />
    </div>
  );
}

export default LinkAggregations;
