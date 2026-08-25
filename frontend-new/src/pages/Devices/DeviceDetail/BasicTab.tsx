/**
 * 基本信息标签页
 * - 设备基本信息展示（只读）
 * - 业务IP展示（支持按条删除、一键清空）
 */

import { useCallback, useMemo } from 'react';
import { Descriptions, Tag, Space, Typography, Button, Popconfirm } from 'antd';
import { DeleteOutlined, ClearOutlined } from '@ant-design/icons';
import type { Device } from '@/types/models';
import {
  DEVICE_STATUS_MAP,
  DeviceStatusCode,
  DEVICE_TYPE_MAP,
  DEVICE_SUBTYPE_LABELS,
  DeviceType
} from '@/types/enums';
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
  const color = entry.isNetwork ? 'blue' : entry.isRange ? 'green' : undefined;
  return (
    <Space size={4} style={{ display: 'inline-flex', marginBottom: 4 }}>
      <Tag color={color} style={{ margin: 0, cursor: 'default' }}>
        {entry.display}
      </Tag>
      {!entry.valid && (
        <Text type="danger" style={{ fontSize: 12 }}>
          (格式错误)
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
  const statusInfo = DEVICE_STATUS_MAP[device.status as DeviceStatusCode];
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
          onSuccess: () => message.success('已删除'),
          onError: () => message.error('删除失败')
        }
      );
    },
    [device.id, device.ip_address, updateDevice, message]
  );

  const handleClearAll = useCallback(() => {
    updateDevice.mutate(
      { id: device.id, ip_address: null },
      {
        onSuccess: () => message.success('已清空所有业务IP'),
        onError: () => message.error('清空失败')
      }
    );
  }, [device.id, updateDevice, message]);

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="设备名称">{device.device_name}</Descriptions.Item>
      <Descriptions.Item label="设备类型">
        {DEVICE_TYPE_MAP[device.device_type as DeviceType]?.label ?? device.device_type}
      </Descriptions.Item>
      <Descriptions.Item label="设备子类型">
        {device.device_subtype
          ? (DEVICE_SUBTYPE_LABELS[device.device_subtype as keyof typeof DEVICE_SUBTYPE_LABELS] ??
            device.device_subtype)
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label="状态">
        <Space size={4}>
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? '未知'}</Tag>
          <DeviceHealthBadge deviceId={device.id} />
        </Space>
      </Descriptions.Item>
      <Descriptions.Item label="品牌">{brandLabel}</Descriptions.Item>
      <Descriptions.Item label="型号">{device.device_model ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="序列号">{device.serial_number ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="主机名">{device.hostname ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="管理IP" span={2}>
        {device.management_ip ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label="业务IP" span={2}>
        {hasIPs ? (
          <Space orientation="vertical" size={0} style={{ width: '100%' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {ipEntries.map((entry, i) => (
                <IPEntryItem key={i} entry={entry} index={i} onRemove={handleRemoveIP} />
              ))}
            </div>
            <Popconfirm
              title="确认清空所有业务IP？"
              onConfirm={handleClearAll}
              okText="确认"
              cancelText="取消"
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<ClearOutlined />}
                style={{ padding: 0, height: 'auto' }}
              >
                清空全部
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          '-'
        )}
      </Descriptions.Item>
      <Descriptions.Item label="所属机房">{device.room_name ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="所属机柜">{device.cabinet_number ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="U位">
        {(device.parent_u_position ?? device.u_position)
          ? `U${device.parent_u_position ?? device.u_position}`
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label="占用U数">{device.height_u}</Descriptions.Item>
      <Descriptions.Item label="客户">{device.customer_name ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="负责人">{device.responsible_person_name ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="CPU">
        {device.cpu
          ? `${device.cpu}${device.cpu_way ? ` ${device.cpu_way}路` : ''}${device.cpu_cores ? ` ${device.cpu_cores}核` : ''}`
          : '-'}
      </Descriptions.Item>
      <Descriptions.Item label="内存">
        {device.memory ? (
          <div>
            <div>{`${device.memory}${device.memory_dimm_count ? ` ×${device.memory_dimm_count}` : ''}`}</div>
            {device.memory_size_gb ? (
              <div style={{ fontSize: 12, color: '#888', lineHeight: 1.6 }}>
                {device.memory_dimm_count
                  ? `单条 ${Math.round(device.memory_size_gb / device.memory_dimm_count)}GB × ${device.memory_dimm_count} = `
                  : ''}
                {device.memory_size_gb}GB
              </div>
            ) : null}
          </div>
        ) : (
          '-'
        )}
      </Descriptions.Item>
      <Descriptions.Item label="GPU">
        {device.gpu ? `${device.gpu}${device.gpu_count ? ` ×${device.gpu_count}` : ''}` : '-'}
      </Descriptions.Item>
      <Descriptions.Item label="操作系统">{device.os_version ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="IPMI地址">{device.ipmi_address ?? '-'}</Descriptions.Item>
      <Descriptions.Item label="功耗">{device.power ? `${device.power}W` : '-'}</Descriptions.Item>
      <Descriptions.Item label="创建时间">{formatDateTime(device.created_at)}</Descriptions.Item>
      <Descriptions.Item label="更新时间">{formatDateTime(device.updated_at)}</Descriptions.Item>
      <Descriptions.Item label="备注" span={2}>
        {device.notes ?? '-'}
      </Descriptions.Item>
    </Descriptions>
  );
}

export default BasicTab;
