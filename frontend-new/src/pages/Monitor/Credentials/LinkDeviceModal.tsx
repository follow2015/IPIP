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
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('monitor');
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
      msg.warning(t('credential.message.selectDeviceRequired'));
      return;
    }
    try {
      await linkExisting.mutateAsync({
        credentialId: selectedCredId!,
        device_ids: linkDeviceIds
      });
      msg.success(t('credential.message.linkedDevices', { count: linkDeviceIds.length }));
      onClose();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : t('credential.message.linkFailed'));
    }
  };

  return (
    <Modal
      title={t('credential.linkTitle')}
      open={open}
      onCancel={onClose}
      onOk={handleConfirmLink}
      confirmLoading={linkExisting.isPending}
      width={480}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }} size="middle">
        <Text type="secondary">
          {t('credential.linkHint', { name: selectedCredName || selectedCredProtocol })}
        </Text>
        <Select
          mode="multiple"
          showSearch
          style={{ width: '100%' }}
          placeholder={t('credential.searchDevicePlaceholder')}
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
          <Text type="secondary">
            {t('credential.selectedDevices', { count: linkDeviceIds.length })}
          </Text>
        )}
      </Space>
    </Modal>
  );
}
