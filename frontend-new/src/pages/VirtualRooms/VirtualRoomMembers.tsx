/**
 * 虚拟机房成员管理（Modal）
 * - Transfer 穿梭框选择交换机
 * - 显示交换机所属机房信息
 */
import { useState, useEffect, useCallback } from 'react';
import { Modal, Transfer, Tag, Space, Spin, Empty } from 'antd';
import { useUpdateVirtualRoomMembers, useVirtualRoom } from '@/services/virtual-room';
import { get } from '@/services/api-client';
import type { VirtualRoom } from '@/types/models';
import type { PaginatedData } from '@/types/api';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

interface VirtualRoomMembersProps {
  open: boolean;
  record: VirtualRoom | null;
  onClose: () => void;
}

interface SwitchOption {
  key: string;
  title: string;
  description: string;
  roomName: string;
  roomId: number;
}

function VirtualRoomMembers({ open, record, onClose }: VirtualRoomMembersProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { t: tn } = useTranslation('network');
  const [targetKeys, setTargetKeys] = useState<string[]>([]);
  const [switchOptions, setSwitchOptions] = useState<SwitchOption[]>([]);
  const [loading, setLoading] = useState(false);
  const updateMembers = useUpdateVirtualRoomMembers();
  const message = useMessage();

  const { data: detail } = useVirtualRoom(record?.id ?? 0, open && !!record);

  const loadSwitches = useCallback(async () => {
    setLoading(true);
    try {
      const res = await get<PaginatedData<{
        device_id: number;
        ip_address: string;
        name?: string;
        room_id?: number;
        room_name?: string;
        has_ssh?: boolean;
      }>>('/switch/list', { page: 1, per_page: 500 });
      const items = (res.data?.items ?? []).filter((sw) => sw.has_ssh === true);
      setSwitchOptions(
        items.map((sw) => ({
          key: String(sw.device_id),
          title: sw.name || sw.ip_address || td('virtualRoom.members.deviceFallback', { id: sw.device_id }),
          description: sw.ip_address || '',
          roomName: sw.room_name || tn('audit.roomFallback', { id: sw.room_id || '?' }),
          roomId: sw.room_id || 0,
        })),
      );
    } catch {
      message.error(td('virtualRoom.message.loadSwitchesFailed'));
    } finally {
      setLoading(false);
    }
  }, [td, tn]);

  useEffect(() => {
    if (open && record) {
      loadSwitches();
    }
  }, [open, record, loadSwitches]);

  useEffect(() => {
    if (detail?.members) {
      setTargetKeys(detail.members.map((m: { device_id: number }) => String(m.device_id)));
    }
  }, [detail]);

  const handleSubmit = async () => {
    if (!record) return;
    try {
      const deviceIds = targetKeys.map((k) => Number(k));
      await updateMembers.mutateAsync({ id: record.id, device_ids: deviceIds });
      message.success(td('virtualRoom.message.membersUpdated'));
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tn('networkList.message.updateFailed'));
    }
  };

  const filterOption = (inputValue: string, option: SwitchOption) =>
    option.title.toLowerCase().includes(inputValue.toLowerCase()) ||
    option.description.toLowerCase().includes(inputValue.toLowerCase()) ||
    option.roomName.toLowerCase().includes(inputValue.toLowerCase());

  return (
    <Modal
      open={open}
      title={record ? td('virtualRoom.members.title', { name: record.name }) : td('virtualRoom.action.manageMembers')}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={updateMembers.isPending}
      destroyOnHidden
      width={720}
      okText={tc('action.save')}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin description={td('virtualRoom.members.loading')} />
        </div>
      ) : switchOptions.length === 0 ? (
        <Empty description={td('virtualRoom.members.empty')} />
      ) : (
        <Transfer<SwitchOption>
          dataSource={switchOptions}
          targetKeys={targetKeys}
          onChange={(keys) => setTargetKeys(keys as string[])}
          render={(item) => (
            <Space size="small">
              <span>{item.title}</span>
              {item.description && (
                <Tag color="blue" style={{ fontSize: 10 }}>
                  {item.description}
                </Tag>
              )}
              <Tag style={{ fontSize: 10 }}>{item.roomName}</Tag>
            </Space>
          )}
          filterOption={filterOption}
          showSearch
          titles={[td('virtualRoom.members.availableTitle'), td('virtualRoom.members.selectedTitle')]}
          listStyle={{ width: 320, height: 400 }}
          oneWay={false}
        />
      )}
    </Modal>
  );
}

export default VirtualRoomMembers;
