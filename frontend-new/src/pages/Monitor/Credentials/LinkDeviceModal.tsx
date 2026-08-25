/**
 * 关联设备到共享凭据 Modal
 *
 * 从 Credentials/index.tsx 拆分（M26）：设备搜索 + 多选关联。
 */
import { useState, useCallback, useEffect } from 'react';
import { Modal, Select, Space, Typography } from 'antd';
import { useLinkExistingCredential, useLinkedDevices, type LinkedDevice } from '@/services/monitor';
import { searchDevicesForLink } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';

const { Text } = Typography;


interface DeviceOption {
  device_id: number;
  device_name: string;
  management_ip: string | null;
}

interface LinkDeviceModalProps {
  open: boolean;
  selectedCredId: number | null;
  selectedCredName: string | undefined;
  selectedCredProtocol: string | undefined;
  onClose: () => void;
}

export default function LinkDeviceModal({
  open,
  selectedCredId,
  selectedCredName,
  selectedCredProtocol,
  onClose
}: LinkDeviceModalProps) {
  const linkExisting = useLinkExistingCredential();
  const msg = useMessage();
  const { data: linkedDevices = [] } = useLinkedDevices(selectedCredId);
  const [linkDeviceIds, setLinkDeviceIds] = useState<number[]>([]);
  const [deviceOptions, setDeviceOptions] = useState<DeviceOption[]>([]);
  const [deviceSearchLoading, setDeviceSearchLoading] = useState(false);

  
  const searchDevices = useCallback(async (keyword: string) => {
    setDeviceSearchLoading(true);
    try {
      const items = (await searchDevicesForLink(keyword)).map((d) => ({
        device_id: d.id,
        device_name: d.device_name,
        management_ip: d.management_ip
      }));
      setDeviceOptions(items);
    } catch {
      setDeviceOptions([]);
    } finally {
      setDeviceSearchLoading(false);
    }
  }, []);

  
  useEffect(() => {
    if (open) {
      setLinkDeviceIds([]);
      searchDevices('');
    }
  }, [open, searchDevices]);

  
  const handleConfirmLink = async () => {
    if (linkDeviceIds.length === 0) {
      msg.warning('请选择至少一台设备');
      return;
    }
    try {
      await linkExisting.mutateAsync({
        credentialId: selectedCredId!,
        device_ids: linkDeviceIds
      });
      msg.success(`已关联 ${linkDeviceIds.length} 台设备`);
      onClose();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '关联失败');
    }
  };

  return (
    <Modal
      title="关联设备到共享凭据"
      open={open}
      onCancel={onClose}
      onOk={handleConfirmLink}
      confirmLoading={linkExisting.isPending}
      width={480}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }} size="middle">
        <Text type="secondary">
          选择要关联到「{selectedCredName || selectedCredProtocol}
          」的设备，已关联的设备不会出现在列表中。
        </Text>
        <Select
          mode="multiple"
          showSearch
          style={{ width: '100%' }}
          placeholder="搜索设备名称或 IP"
          filterOption={false}
          onSearch={searchDevices}
          loading={deviceSearchLoading}
          value={linkDeviceIds}
          onChange={setLinkDeviceIds}
          options={deviceOptions
            .filter((d) => !linkedDevices.some((ld) => ld.device_id === d.device_id))
            .map((d) => ({
              value: d.device_id,
              label: `${d.device_name}${d.management_ip ? ` (${d.management_ip})` : ''}`
            }))}
        />
        {linkDeviceIds.length > 0 && (
          <Text type="secondary">已选 {linkDeviceIds.length} 台设备</Text>
        )}
      </Space>
    </Modal>
  );
}
