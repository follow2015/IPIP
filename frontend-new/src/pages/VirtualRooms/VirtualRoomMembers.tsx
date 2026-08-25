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
          title: sw.name || sw.ip_address || `设备#${sw.device_id}`,
          description: sw.ip_address || '',
          roomName: sw.room_name || `机房#${sw.room_id || '?'}`,
          roomId: sw.room_id || 0,
        })),
      );
    } catch {
      message.error('加载交换机列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

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
      message.success('成员更新成功');
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新失败');
    }
  };

  const filterOption = (inputValue: string, option: SwitchOption) =>
    option.title.toLowerCase().includes(inputValue.toLowerCase()) ||
    option.description.toLowerCase().includes(inputValue.toLowerCase()) ||
    option.roomName.toLowerCase().includes(inputValue.toLowerCase());

  return (
    <Modal
      open={open}
      title={record ? `管理成员 - ${record.name}` : '管理成员'}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={updateMembers.isPending}
      destroyOnHidden
      width={720}
      okText="保存"
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin description="加载交换机列表..." />
        </div>
      ) : switchOptions.length === 0 ? (
        <Empty description="暂无可用交换机" />
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
          titles={['可选交换机', '已选成员']}
          listStyle={{ width: 320, height: 400 }}
          oneWay={false}
        />
      )}
    </Modal>
  );
}

export default VirtualRoomMembers;
