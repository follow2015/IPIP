/**
 * 基本信息标签页
 * - 设备基本信息展示（只读）
 * - 业务IP展示（支持按条删除、一键清空）
 */

import { useCallback, useMemo } from 'react';
import { useConfirm } from '@/utils/confirm';
import { Descriptions, Tag, Space, Typography, Button } from 'antd';
import { DeleteOutlined, ClearOutlined } from '@ant-design/icons';
import type { Device } from '@/types/models';
import { DeviceType } from '@/types/enums';
import {
  getDeviceStatusMeta,
  getDeviceSubtypeLabel,
  getDeviceTypeMeta
} from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';
import { parseIPAddressString, removeIPAtIndex, type ParsedIPEntry } from '@/utils/ip';
import { useUpdateDevice } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import { useVendorBrands } from '@/services/monitor';
import DeviceHealthBadge from '@/components/DeviceHealthBadge/DeviceHealthBadge';

const { Text } = Typography;

interface BasicTabProps {
  device: Device;
}

function IPEntryItem({
  entry,
  index,
  onRemove
}: {
  entry: ParsedIPEntry;
  index: number;
  onRemove: (index: number) => void;
}) {
  const { t } = useTranslation('device');
  const color = entry.isNetwork ? 'blue' : entry.isRange ? 'green' : undefined;
  return (
    <Space size={4} style={{ display: 'inline-flex', marginBottom: 4 }}>
      <Tag color={color} style={{ margin: 0, cursor: 'default' }}>
        {entry.display}
      </Tag>
      {!entry.valid && (
        <Text type="danger" style={{ fontSize: 12 }}>
          {t('basic.invalidFormat')}
        </Text>
      )}
      <Button
        type="text"
        size="small"
        danger
        icon={<DeleteOutlined />}
        onClick={() => onRemove(index)}
        style={{ padding: '0 2px', minWidth: 20 }}
      />
    </Space>
  );
}

function BasicTab({ device }: BasicTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const statusInfo = getDeviceStatusMeta(device.status, t);
  const updateDevice = useUpdateDevice();
  const message = useMessage();
  const { data: vendorBrands } = useVendorBrands();
  const brandLabel = useMemo(() => {
    if (!device.brand) return '-';
    const found = (vendorBrands?.items ?? []).find(
      (v) => v.enterprise_no === device.brand && v.enabled
    );
    return found?.label ?? device.brand;
  }, [device.brand, vendorBrands]);

  const ipEntries = useMemo(() => parseIPAddressString(device.ip_address), [device.ip_address]);
  const hasIPs = ipEntries.length > 0;

  const handleRemoveIP = useCallback(
    (index: number) => {
      const newIpString = removeIPAtIndex(device.ip_address, index);
      updateDevice.mutate(
        { id: device.id, ip_address: newIpString || null },
        {
          onSuccess: () => message.success(t('basic.message.ipDeleted')),
          onError: () => message.error(tCommon('message.deleteFailed'))
        }
      );
    },
    [device.id, device.ip_address, updateDevice, message, t, tCommon]
  );

  const handleClearAll = useCallback(() => {
    updateDevice.mutate(
      { id: device.id, ip_address: null },
      {
        onSuccess: () => message.success(t('basic.message.cleared')),
        onError: () => message.error(t('basic.message.clearFailed'))
      }
    );
  }, [device.id, updateDevice, message, t]);

  return (
    <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
      <Descriptions.Item label={t('field.name')}>{device.device_name}</Descriptions.Item>
      <Descriptions.Item label={t('basic.field.deviceType')}>
        {getDeviceTypeMeta(device.device_type as DeviceType, t)?.label ?? device.device_type}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.deviceSubtype')}>
        {device.device_subtype
          ? (getDeviceSubtypeLabel(device.device_subtype, t) ?? device.device_subtype)
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label={tCommon('field.status')}>
        <Space size={4}>
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? t('status.unknown')}</Tag>
          <DeviceHealthBadge deviceId={device.id} />
        </Space>
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.brand')}>{brandLabel}</Descriptions.Item>
      <Descriptions.Item label={t('basic.field.model')}>
        {device.device_model ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.serialNumber')}>
        {device.serial_number ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('node.column.hostname')}>{device.hostname ?? '-'}</Descriptions.Item>
      <Descriptions.Item label={t('field.managementIp')} span={2}>
        {device.management_ip ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.businessIp')} span={2}>
        {hasIPs ? (
          <Space orientation="vertical" size={0} style={{ width: '100%' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {ipEntries.map((entry, i) => (
                <IPEntryItem key={i} entry={entry} index={i} onRemove={handleRemoveIP} />
              ))}
            </div>
            <Button
              type="link"
              size="small"
              danger
              icon={<ClearOutlined />}
              style={{ padding: 0, height: 'auto' }}
              onClick={() =>
                confirm({
                  title: t('basic.confirmClear'),
                  okText: tCommon('action.confirm'),
                  cancelText: tCommon('action.cancel'),
                  okButtonProps: { danger: true },
                  onOk: handleClearAll
                })
              }
            >
              {t('basic.clearAll')}
            </Button>
          </Space>
        ) : (
          '-'
        )}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.room')}>{device.room_name ?? '-'}</Descriptions.Item>
      <Descriptions.Item label={t('field.cabinet')}>
        {device.cabinet_number ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('field.uPosition')}>
        {(device.parent_u_position ?? device.u_position)
          ? `U${device.parent_u_position ?? device.u_position}`
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.occupiedU')}>{device.height_u}</Descriptions.Item>
      <Descriptions.Item label={tCommon('field.customer')}>
        {device.customer_name ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.owner')}>
        {device.responsible_person_name ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.cpu')}>
        {device.cpu
          ? `${device.cpu}${device.cpu_way ? ` ${t('basic.cpu.way', { count: device.cpu_way })}` : ''}${device.cpu_cores ? ` ${t('basic.cpu.cores', { count: device.cpu_cores })}` : ''}`
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('field.memory')}>
        {device.memory ? (
          <div>
            <div>{`${device.memory}${device.memory_dimm_count ? ` ×${device.memory_dimm_count}` : ''}`}</div>
            {device.memory_size_gb ? (
              <div style={{ fontSize: 12, color: '#888', lineHeight: 1.6 }}>
                {device.memory_dimm_count
                  ? t('basic.field.memoryPerDimm', {
                      size: Math.round(device.memory_size_gb / device.memory_dimm_count),
                      count: device.memory_dimm_count
                    })
                  : ''}
                {device.memory_size_gb}GB
              </div>
            ) : null}
          </div>
        ) : (
          '-'
        )}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.gpu')}>
        {device.gpu ? `${device.gpu}${device.gpu_count ? ` ×${device.gpu_count}` : ''}` : '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('hardware.os.label')}>{device.os_version ?? '-'}</Descriptions.Item>
      <Descriptions.Item label={t('hardware.ipmi.address')}>
        {device.ipmi_address ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('basic.field.power')}>
        {device.power ? `${device.power}W` : '-'}
      </Descriptions.Item>
      <Descriptions.Item label={tCommon('field.createdAt')}>
        {formatDateTime(device.created_at)}
      </Descriptions.Item>
      <Descriptions.Item label={tCommon('field.updatedAt')}>
        {formatDateTime(device.updated_at)}
      </Descriptions.Item>
      <Descriptions.Item label={tCommon('field.remarks')} span={2}>
        {device.notes ?? '-'}
      </Descriptions.Item>
    </Descriptions>
  );
}

export default BasicTab;
