/**
 * 虚拟机房管理页面
 * - 列表查询、新增、编辑、删除
 * - 成员管理（选择交换机）
 * - 触发扫描 + 扫描进度
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useConfirm } from '@/utils/confirm';
import { Button, Tag, Space, Tooltip, Progress } from 'antd';
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
import { useTranslation } from 'react-i18next';

function VirtualRooms() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { t: tn } = useTranslation('network');
  const confirm = useConfirm();
  const members = useDisclosure();
  const [membersRecord, setMembersRecord] = useState<VirtualRoom | null>(null);
  const [scanningId, setScanningId] = useState<number | null>(null);
  const scanVirtualRoom = useScanVirtualRoom();
  const message = useMessage();

  const crud = useCrudPage<VirtualRoom>({
    useList: useVirtualRooms,
    useDelete: useDeleteVirtualRoom,
    nameKey: 'name',
    nameLabel: td('virtualRoom.name')
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
    members.open();
  };

  const handleScan = async (record: VirtualRoom) => {
    try {
      await scanVirtualRoom.mutateAsync(record.id);
      setScanningId(record.id);
      message.info(td('virtualRoom.message.scanSubmitted'));
    } catch (err: unknown) {
      const errorMsg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        (err instanceof Error ? err.message : tn('ip.message.scanNetworkFailed'));
      message.error(errorMsg);
    }
  };

  const columns = [
    {
      title: td('virtualRoom.field.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: VirtualRoom) => (
        <Button type="link" size="small" onClick={() => handleMembers(record)}>
          {name}
        </Button>
      )
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string | null) => v || '-'
    },
    {
      title: td('lag.column.memberCount'),
      key: 'member_count',
      width: 80,
      align: 'center' as const,
      render: (_: unknown, record: VirtualRoom) => record.member_count ?? 0
    },
    {
      title: td('virtualRoom.field.lastScan'),
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
              title={td('virtualRoom.scanProgressTooltip', {
                phase: scanProgress.phase,
                completed: scanProgress.completed,
                total: scanProgress.total,
                failed: scanProgress.failed
              })}
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
        return <Tag>{td('virtualRoom.notScanned')}</Tag>;
      }
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
      width: 240,
      render: (_: unknown, record: VirtualRoom) => (
        <Space size="small">
          <Tooltip title={td('virtualRoom.action.manageMembers')}>
            <Button
              type="link"
              size="small"
              icon={<TeamOutlined />}
              onClick={() => handleMembers(record)}
            />
          </Tooltip>
          <Tooltip title={td('virtualRoom.action.scan')}>
            <Button
              type="link"
              size="small"
              icon={<ThunderboltOutlined />}
              loading={scanningId === record.id}
              disabled={scanningId !== null && scanningId !== record.id}
              onClick={() =>
                confirm({
                  title: td('virtualRoom.confirm.scanTitle'),
                  content: td('virtualRoom.confirm.scanContent', { name: record.name }),
                  okText: td('virtualRoom.action.startScan'),
                  cancelText: tc('action.cancel'),
                  onOk: () => handleScan(record)
                })
              }
            />
          </Tooltip>
          <Tooltip title={tc('action.edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip title={tc('action.delete')}>
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
        searchPlaceholder={td('virtualRoom.searchPlaceholder')}
        toolbar={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              {td('virtualRoom.add')}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
              {tc('action.refresh')}
            </Button>
          </Space>
        }
      />
      <VirtualRoomForm open={formOpen} editRecord={editRecord} onClose={closeForm} />
      <VirtualRoomMembers
        open={members.isOpen}
        record={membersRecord}
        onClose={() => {
          members.close();
          setMembersRecord(null);
          refetch();
        }}
      />
    </div>
  );
}

export default VirtualRooms;
