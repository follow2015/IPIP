import { useConfirm } from '@/utils/confirm';
import { useState, useEffect, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Tabs, Spin, Button, Space, Tag, Dropdown, Descriptions, Result } from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
  SwapOutlined,
  CopyOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useDeviceSuspenseDetail, useDeleteDevice, useUpdateDeviceStatus } from '@/services/device';
import { useSwitchWithPorts, useSyncSwitchInfo } from '@/services/switch';

import { DEVICE_SUBTYPE_COLORS, DeviceType, DeviceSubtype } from '@/types/enums';
import {
  getDeviceStatusMeta,
  getDeviceStatusOptions,
  getDeviceSubtypeLabel,
  getDeviceTypeMeta,
  getSwitchRoleMeta
} from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import type { RenderPortActionsFn, RenderBatchActionsFn } from '@/types/port';
import SwitchForm from './SwitchForm';
import PortActions from './PortActions';
import BatchPortActions from './BatchPortActions';
import DeviceForm from '@/pages/Devices/DeviceForm';
import BasicTab from '@/pages/Devices/DeviceDetail/BasicTab';
import UnifiedPortTab from '@/pages/Devices/DeviceDetail/UnifiedPortTab';
import VlanTab from '@/pages/Devices/DeviceDetail/VlanTab';
import LagTab from '@/pages/Devices/DeviceDetail/LagTab';
import ConnectionTab from '@/pages/Devices/DeviceDetail/ConnectionTab';
import StorageTab from '@/pages/Devices/DeviceDetail/StorageTab';
import AssetTab from '@/pages/Devices/DeviceDetail/AssetTab';
import CredentialTab from '@/pages/Devices/DeviceDetail/CredentialTab';
import MetricsTab from '@/pages/Devices/DeviceDetail/MetricsTab';

function SwitchDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('device');
  const switchId = Number(id);

  if (Number.isNaN(switchId)) {
    return (
      <Result
        status="404"
        title={t('detail.invalidParam')}
        subTitle={t('switch.invalidIdSubTitle')}
        extra={<Button onClick={() => navigate(-1)}>{t('detail.backToList')}</Button>}
      />
    );
  }

  return <SwitchDetailContent switchId={switchId} />;
}

function SwitchDetailContent({ switchId }: { switchId: number }) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const location = useLocation();
  const navigate = useNavigate();

  const hashTabKey = location.hash.replace('#', '') || undefined;
  const [activeTabKey, setActiveTabKey] = useState<string>(hashTabKey ?? 'basic');

  useEffect(() => {
    if (hashTabKey) {
      setActiveTabKey(hashTabKey);
    }
  }, [hashTabKey]);

  const { data: device, refetch } = useDeviceSuspenseDetail(switchId);
  const { data: switchWithPorts, isLoading: switchLoading } = useSwitchWithPorts(switchId);
  const switchData = switchWithPorts?.switch;
  const hasSsh = switchData?.has_ssh ?? false;

  const deleteDevice = useDeleteDevice();
  const updateStatus = useUpdateDeviceStatus();
  const message = useMessage();

  const form = useDisclosure();
  const deviceForm = useDisclosure();

  const syncSwitchInfo = useSyncSwitchInfo();
  const handleRefreshDeviceInfo = () => {
    confirm({
      title: td('detail.refreshInfo'),
      content: td('detail.refreshInfoContent'),
      okText: tc('action.ok'),
      cancelText: tc('action.cancel'),
      onOk: async () => {
        try {
          await syncSwitchInfo.mutateAsync(switchId);
          message.info(td('detail.refreshInfoSubmitted'));
        } catch {
          message.error(td('switch.refreshInfoSubmitFailed'));
        }
      }
    });
  };

  const handleDeviceEvent = useCallback(
    (event: any) => {
      if (event.op_type === 'info_refresh') {
        refetch();
      }
      if (event.op_type === 'scan_complete') {
        refetch();
      }
      if (event.op_type === 'port_sync' && event.affected_ports?.includes('*')) {
        refetch();
      }
    },
    [refetch]
  );

  useDeviceEvents(switchId, 'ports' as const, handleDeviceEvent);

  const renderPortActions: RenderPortActionsFn = useCallback(
    (port, { refetch, submitAction }) => (
      <PortActions
        switchId={switchId}
        port={port}
        onRefresh={refetch}
        submitAction={submitAction}
        hasSsh={hasSsh}
      />
    ),
    [switchId, hasSsh]
  );
  const renderBatchActions: RenderBatchActionsFn = useCallback(
    ({ selectedPorts, onClearSelection, hasSsh, refetch, onBatchLocalUpdate }) => (
      <BatchPortActions
        switchId={switchId}
        selectedPorts={selectedPorts}
        onClearSelection={onClearSelection}
        onRefresh={refetch}
        hasSsh={hasSsh}
        onBatchLocalUpdate={onBatchLocalUpdate}
      />
    ),
    [switchId]
  );

  if (switchLoading)
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!device) return <div>{td('detail.notFound')}</div>;

  const handleDelete = () => {
    confirm({
      title: tc('confirm.deleteTitle'),
      content: td('switch.deleteContent', { name: device.device_name }),
      okText: tc('action.ok'),
      cancelText: tc('action.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteDevice.mutateAsync(device.id);
        message.success(tc('message.deleteSuccess'));
        navigate('/switches');
      }
    });
  };

  const handleStatusChange = (newStatus: number) => {
    updateStatus.mutateAsync({ id: device.id, status: newStatus }).then(() => {
      message.success(td('detail.statusChanged'));
      refetch();
    });
  };

  const handleCopyDetail = () => {
    if (!switchData) return;
    const text = [
      td('switch.copy.header'),
      '==================',
      td('switch.copy.name', { value: switchData.name }),
      td('switch.copy.ip', { value: switchData.ip_address ?? '-' }),
      td('switch.copy.port', { value: switchData.port ?? 22 }),
      td('switch.copy.username', { value: switchData.username ?? '-' }),
      td('switch.copy.protocol', { value: switchData.protocol ?? 'SSH' }),
      td('switch.copy.deviceType', { value: switchData.device_type ?? '-' }),
      td('switch.copy.deviceModel', { value: switchData.device_model ?? '-' }),
      td('switch.copy.room', { value: switchData.room_name ?? '-' }),
      td('switch.copy.version', { value: switchData.device_version ?? '-' }),
      td('switch.copy.serial', { value: switchData.device_serial ?? '-' }),
      td('switch.copy.uptime', { value: switchData.device_uptime ?? '-' }),
      td('switch.copy.mac', {
        value: switchData.mac_address?.length ? switchData.mac_address.join(', ') : '-'
      })
    ].join('\n');
    navigator.clipboard.writeText(text).then(() =>
      message.success(td('switch.detailCopied'))
    );
  };

  const tabItems = [];

  tabItems.push({
    key: 'basic',
    label: td('tab.basic'),
    children: (
      <div>
        <BasicTab device={device} />
        {/* 交换机专属信息 */}
        {switchData && (
          <Descriptions
            title={td('form.section.switchConfig')}
            column={{ xs: 1, md: 2 }}
            bordered
            size="small"
            style={{ marginTop: 16 }}
          >
            <Descriptions.Item label={td('field.managementIp')}>
              {switchData.ip_address ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.sshPort')}>
              {switchData.port ?? 22}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.protocol')}>
              {switchData.protocol ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('credential.form.username')}>
              {switchData.username ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.deviceDriver')}>
              {switchData.device_type ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.role.label')}>
              {getSwitchRoleMeta(switchData.switch_role, td)?.label ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.layer')}>
              {switchData.layer != null ? `L${switchData.layer}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.portCount.placeholder')}>
              {switchData.port_num ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.uplinkDevice.label')}>
              {switchData.uplink_device_name ??
                (switchData.uplink_device_id ? `ID:${switchData.uplink_device_id}` : '-')}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.uplinkPorts.label')}>
              {switchData.uplink_port_names?.length ? switchData.uplink_port_names.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.peerPorts.label')}>
              {switchData.peer_port_names?.length ? switchData.peer_port_names.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.networkTopology.coreDevice.label')}>
              {switchData.core_device_name ??
                (switchData.core_device_id ? `ID:${switchData.core_device_id}` : '-')}
            </Descriptions.Item>
            <Descriptions.Item label={td('node.column.hostname')}>
              {switchData.hostname ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.version')}>
              {switchData.device_version ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('basic.field.serialNumber')}>
              {switchData.device_serial ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.uptime')}>
              {switchData.device_uptime ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.field.mac')}>
              {switchData.mac_address?.length ? switchData.mac_address.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('form.network.managementAccess.label')}>
              {hasSsh ? <Tag color="green">{td('switch.sshEnabled')}</Tag> : <Tag>{td('tooltip.recordOnly')}</Tag>}
            </Descriptions.Item>
          </Descriptions>
        )}
      </div>
    )
  });

  tabItems.push({
    key: 'ports',
    label: td('tab.ports'),
    children: (
      <UnifiedPortTab
        deviceId={switchId}
        hasSsh={hasSsh}
        renderPortActions={renderPortActions}
        renderBatchActions={renderBatchActions}
      />
    )
  });

  tabItems.push({
    key: 'vlans',
    label: td('tab.vlans'),
    children: <VlanTab deviceId={switchId} hasSsh={hasSsh} />
  });

  tabItems.push({
    key: 'lag',
    label: td('tab.lag'),
    children: <LagTab deviceId={switchId} hasSsh={hasSsh} />
  });

  tabItems.push({
    key: 'connections',
    label: td('tab.connections'),
    children: <ConnectionTab device={device} />
  });

  tabItems.push({
    key: 'storage',
    label: td('tab.storage'),
    children: <StorageTab deviceId={switchId} />
  });

  tabItems.push({
    key: 'asset',
    label: td('tab.asset'),
    children: <AssetTab device={device} />
  });

  tabItems.push({
    key: 'metrics',
    label: td('metric.title'),
    children: <MetricsTab deviceId={switchId} />
  });

  tabItems.push({
    key: 'credentials',
    label: td('tab.credentials'),
    children: <CredentialTab device={device} />
  });

  const statusInfo = getDeviceStatusMeta(device.status, td);

  const statusMenuItems = getDeviceStatusOptions(td)
    .filter((o) => o.value !== device.status)
    .map((o) => ({
      key: String(o.value),
      label: o.label
    }));

  const subtypeTag = device.device_subtype ? (
    <Tag color={DEVICE_SUBTYPE_COLORS[device.device_subtype as DeviceSubtype] ?? 'default'}>
      {getDeviceSubtypeLabel(device.device_subtype, td) ?? device.device_subtype}
    </Tag>
  ) : null;

  return (
    <div>
      {/* 顶部导航栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/switches')}>
          {td('detail.backToList')}
        </Button>
        <Space>
          <Button icon={<CopyOutlined />} onClick={handleCopyDetail}>
            {td('switch.copyDetail')}
          </Button>
          <Dropdown
            menu={{ items: statusMenuItems, onClick: ({ key }) => handleStatusChange(Number(key)) }}
          >
            <Button icon={<SwapOutlined />}>{td('detail.changeStatus')}</Button>
          </Dropdown>
          {hasSsh && (
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshDeviceInfo}
              loading={syncSwitchInfo.isPending}
            >
              {td('detail.refreshInfo')}
            </Button>
          )}
          {hasSsh && (
            <Button type="primary" icon={<EditOutlined />} onClick={() => form.open()}>
              {td('switch.remoteInfo')}
            </Button>
          )}
          <Button icon={<EditOutlined />} onClick={() => deviceForm.open()}>
            {tc('action.edit')}
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            {tc('action.delete')}
          </Button>
        </Space>
      </div>

      {/* 设备概要 */}
      <Descriptions column={{ xs: 1, md: 3 }} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label={td('field.name')}>
          <strong style={{ fontSize: 16 }}>{device.device_name}</strong>
        </Descriptions.Item>
        <Descriptions.Item label={tc('field.type')}>
          <Space>
            <Tag>
              {getDeviceTypeMeta(device.device_type as DeviceType, td)?.label ??
                device.device_type}
            </Tag>
            {subtypeTag}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={tc('field.status')}>
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? td('status.unknown')}</Tag>
        </Descriptions.Item>
      </Descriptions>

      <Tabs
        activeKey={activeTabKey}
        onChange={(key) => {
          setActiveTabKey(key);
          navigate(`${location.pathname}#${key}`, { replace: true });
        }}
        items={tabItems}
      />

      {/* 编辑表单（简化版，仅交换机配置） */}
      <SwitchForm
        open={form.isOpen}
        editRecord={switchData ?? null}
        onClose={() => {
          form.close();
          refetch();
        }}
      />

      {/* 完整编辑表单（DeviceForm） */}
      <DeviceForm
        open={deviceForm.isOpen}
        editRecord={null}
        editDeviceId={device.id}
        onClose={() => {
          deviceForm.close();
          refetch();
        }}
      />
    </div>
  );
}

export default SwitchDetail;
