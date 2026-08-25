/**
 * 虚拟机房管理页面
 * - 列表查询、新增、编辑、删除
 * - 成员管理（选择交换机）
 * - 触发扫描 + 扫描进度
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Tag, Space, Tooltip, Progress, Popconfirm } from 'antd';
import {
  PlusOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import VirtualRoomForm from './VirtualRoomForm';
import VirtualRoomMembers from './VirtualRoomMembers';
import {
  useVirtualRooms,
  useDeleteVirtualRoom,
  useScanVirtualRoom,
  useVirtualRoomScanProgress
} from '@/services/virtual-room';
import type { VirtualRoom } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { formatDateTime } from '@/utils/format';
import { useMessage } from '@/hooks/useMessage';
import { useGlobalEventListener } from '@/hooks/useGlobalEvents';
import type { GlobalEvent } from '@/hooks/useGlobalEvents';

function VirtualRooms() {
  const [membersOpen, setMembersOpen] = useState(false);
  const [membersRecord, setMembersRecord] = useState<VirtualRoom | null>(null);
  const [scanningId, setScanningId] = useState<number | null>(null);
  const scanVirtualRoom = useScanVirtualRoom();
  const message = useMessage();

  const crud = useCrudPage<VirtualRoom>({
    useList: useVirtualRooms,
    useDelete: useDeleteVirtualRoom,
    nameKey: 'name',
    nameLabel: '虚拟机房'
  });
  const {
    table,
    data,
    isLoading,
    refetch,
    handleAdd,
    handleEdit,
    handleDelete,
    closeForm,
    formOpen,
    editRecord
  } = crud;

  useGlobalEventListener(
    useCallback(
      (event: GlobalEvent) => {
        if (event.event_type === 'room_scan_complete') {
          const payload = event.payload as Record<string, unknown>;
          const vrId = payload.virtual_room_id as number | undefined;
          if (vrId && scanningId === vrId) {
            setScanningId(null);
            refetch();
          }
        }
      },
      [scanningId, refetch]
    )
  );

  const { data: progressData } = useVirtualRoomScanProgress(scanningId ?? 0, scanningId !== null);
  const scanProgress = progressData?.progress;

  const lastFailedRef = useRef<number | null>(null);
  useEffect(() => {
    if (!scanProgress || !scanningId) return;
    if (scanProgress.phase === 'failed') {
      if (lastFailedRef.current === scanningId) return;
      lastFailedRef.current = scanningId;
      setScanningId(null);
      refetch();
    }
  }, [scanProgress, scanningId, refetch]);

  const handleMembers = (record: VirtualRoom) => {
    setMembersRecord(record);
    setMembersOpen(true);
  };

  const handleScan = async (record: VirtualRoom) => {
    try {
      await scanVirtualRoom.mutateAsync(record.id);
      setScanningId(record.id);
      message.info('虚拟机房扫描已提交，完成后将通过消息通知您');
    } catch (err: unknown) {
      const errorMsg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        (err instanceof Error ? err.message : '扫描启动失败');
      message.error(errorMsg);
    }
  };

  const columns = [
    {
      title: '虚拟机房名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: VirtualRoom) => (
        <Button type="link" size="small" onClick={() => handleMembers(record)}>
          {name}
        </Button>
      )
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string | null) => v || '-'
    },
    {
      title: '成员数',
      key: 'member_count',
      width: 80,
      align: 'center' as const,
      render: (_: unknown, record: VirtualRoom) => record.member_count ?? 0
    },
    {
      title: '最近扫描',
      key: 'last_scan',
      width: 180,
      render: (_: unknown, record: VirtualRoom) => {
        if (scanningId === record.id && scanProgress) {
          const percent =
            scanProgress.total > 0
              ? Math.round(
                  ((scanProgress.completed + scanProgress.failed) / scanProgress.total) * 100
                )
              : 0;
          return (
            <Tooltip
              title={`阶段: ${scanProgress.phase} | 完成: ${scanProgress.completed}/${scanProgress.total} | 失败: ${scanProgress.failed}`}
            >
              <Progress
                percent={percent}
                size="small"
                status={scanProgress.failed > 0 ? 'exception' : 'active'}
                format={() => scanProgress.phase}
              />
            </Tooltip>
          );
        }
        if (record.last_scan_at) {
          return (
            <span>
              {formatDateTime(record.last_scan_at)}
              {record.last_scan_scope && (
                <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>
                  {record.last_scan_scope.startsWith('vr:') ? 'VR' : 'R'}
                </Tag>
              )}
            </span>
          );
        }
        return <Tag>未扫描</Tag>;
      }
    },
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
      width: 240,
      render: (_: unknown, record: VirtualRoom) => (
        <Space size="small">
          <Tooltip title="管理成员">
            <Button
              type="link"
              size="small"
              icon={<TeamOutlined />}
              onClick={() => handleMembers(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认扫描？"
            description={`将对虚拟机房「${record.name}」下的所有交换机执行全量扫描`}
            onConfirm={() => handleScan(record)}
            okText="开始扫描"
            cancelText="取消"
          >
            <Tooltip title="触发扫描">
              <Button
                type="link"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={scanningId === record.id}
                disabled={scanningId !== null && scanningId !== record.id}
              />
            </Tooltip>
          </Popconfirm>
          <Tooltip title="编辑">
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      )
    }
  ];

  return (
    <div>
      <DataTable<VirtualRoom>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="id"
        total={data?.total}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={() => {
          setScanningId(null);
          refetch();
        }}
        searchPlaceholder="搜索虚拟机房名称"
        toolbar={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              新增虚拟机房
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
              刷新
            </Button>
          </Space>
        }
      />
      <VirtualRoomForm open={formOpen} editRecord={editRecord} onClose={closeForm} />
      <VirtualRoomMembers
        open={membersOpen}
        record={membersRecord}
        onClose={() => {
          setMembersOpen(false);
          setMembersRecord(null);
          refetch();
        }}
      />
    </div>
  );
}

export default VirtualRooms;
