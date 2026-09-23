import { useConfirm } from '@/utils/confirm';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tabs, Spin, Button, Space, Tag, Dropdown, Descriptions, Result } from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
  SwapOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useDeviceSuspenseDetail, useDeleteDevice, useUpdateDeviceStatus } from '@/services/device';
import { DEVICE_SUBTYPE_COLORS, DeviceType, DeviceSubtype } from '@/types/enums';
import {
  getDeviceStatusMeta,
  getDeviceStatusOptions,
  getDeviceSubtypeLabel,
  getDeviceTypeMeta
} from '@/types/statusMeta';
import { useMessage } from '@/hooks/useMessage';
import { useSyncSwitchInfo } from '@/services/switch';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import DeviceForm from '../DeviceForm';
import BasicTab from './BasicTab';
import NicTab from './NicTab';
import UnifiedPortTab from './UnifiedPortTab';
import VlanTab from './VlanTab';
import LagTab from './LagTab';
import ConnectionTab from './ConnectionTab';
import StorageTab from './StorageTab';
import AssetTab from './AssetTab';
import NodeTab from './NodeTab';
import CredentialTab from './CredentialTab';
import MetricsTab from './MetricsTab';
import { getCategoryConfig } from '../shared/categoryConfig';
import type { TabKey } from '../shared/categoryConfig';

function DeviceDetail() {
  const { t: tDevice } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const deviceId = Number(id);

  if (Number.isNaN(deviceId)) {
    return (
      <Result
        status="404"
        title={tDevice('detail.invalidParam')}
        subTitle={tDevice('detail.invalidDeviceId')}
        extra={<Button onClick={() => navigate(-1)}>{tCommon('action.back')}</Button>}
      />
    );
  }

  return <DeviceDetailContent deviceId={deviceId} />;
}

function DeviceDetailContent({ deviceId }: { deviceId: number }) {
  const confirm = useConfirm();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: device, refetch } = useDeviceSuspenseDetail(deviceId);
  const { t: tDevice } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const deleteDevice = useDeleteDevice();
  const updateStatus = useUpdateDeviceStatus();
  const message = useMessage();

  const hashTabKey = location.hash.replace('#', '') || undefined;
  const [activeTabKey, setActiveTabKey] = useState<string>(hashTabKey ?? 'basic');

  useEffect(() => {
    setActiveTabKey(hashTabKey ?? 'basic');
  }, [hashTabKey]);

  const isNetworkDevice = device?.device_type === DeviceType.NETWORK;
  const hasSsh = !!device.switch_credential?.has_ssh;

  useDeviceEvents(
    deviceId,
    'ports',
    useCallback(
      (event) => {
        if (event.op_type === 'info_refresh' && event.success !== false) {
          refetch();
        }
      },
      [refetch]
    ),
    isNetworkDevice
  );

  const syncSwitchInfo = useSyncSwitchInfo();
  const handleRefreshDeviceInfo = () => {
    confirm({
      title: tDevice('detail.refreshInfo'),
      content: tDevice('detail.refreshInfoContent'),
      onOk: async () => {
        try {
          await syncSwitchInfo.mutateAsync(deviceId);
          message.info(tDevice('detail.refreshInfoSubmitted'));
        } catch {
        }
      }
    });
  };

  const form = useDisclosure();

  if (!device) {
    return <div>{tDevice('detail.notFound')}</div>;
  }

  const handleDelete = () => {
    confirm({
      title: tCommon('confirm.deleteTitle'),
      content: tDevice('confirm.deleteContent', { name: device.device_name }),
      okText: tCommon('action.ok'),
      cancelText: tCommon('action.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(device.id);
          message.success(tCommon('message.deleteSuccess'));
          navigate('/devices');
        } catch (err) {
          message.error(err instanceof Error ? err.message : tCommon('message.deleteFailed'));
        }
      }
    });
  };

  const handleStatusChange = async (newStatus: number) => {
    try {
      await updateStatus.mutateAsync({ id: device.id, status: newStatus });
      message.success(tDevice('detail.statusChanged'));
      refetch();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tDevice('detail.statusChangeFailed'));
    }
  };

  const category = getCategoryConfig(device.device_type as DeviceType);

  const renderTab = (key: TabKey) => {
    const hasSsh = !!device.switch_credential?.has_ssh;
    switch (key) {
      case 'basic':
        return <BasicTab device={device} />;
      case 'nics':
        return <NicTab deviceId={deviceId} />;
      case 'ports':
        return <UnifiedPortTab deviceId={deviceId} hasSsh={hasSsh} />;
      case 'vlans':
        return <VlanTab deviceId={deviceId} hasSsh={hasSsh} />;
      case 'lag':
        return <LagTab deviceId={deviceId} hasSsh={hasSsh} />;
      case 'connections':
        return <ConnectionTab device={device} />;
      case 'storage':
        return <StorageTab deviceId={deviceId} />;
      case 'asset':
        return <AssetTab device={device} />;
      case 'nodes':
        return (
          <NodeTab
            deviceId={deviceId}
            deviceName={device.device_name}
            totalNodes={device.total_nodes ?? undefined}
            nodeRows={device.node_rows ?? undefined}
            nodeCols={device.node_cols ?? undefined}
          />
        );
      case 'metrics':
        return <MetricsTab deviceId={deviceId} />;
      case 'credentials':
        return <CredentialTab device={device} />;
    }
  };

  const tabItems = category.detailTabs
    .filter((t) => (t.when ? t.when(device) : true))
    .map((t) => ({
      key: t.key,
      label: tDevice(t.labelKey),
      children: renderTab(t.key)
    }));

  const statusInfo = getDeviceStatusMeta(device.status, tDevice);

  const statusMenuItems = getDeviceStatusOptions(tDevice)
    .filter((o) => o.value !== device.status)
    .map((o) => ({
      key: String(o.value),
      label: o.label
    }));

  const subtypeTag = device.device_subtype ? (
    <Tag color={DEVICE_SUBTYPE_COLORS[device.device_subtype as DeviceSubtype] ?? 'default'}>
      {getDeviceSubtypeLabel(device.device_subtype as DeviceSubtype, tDevice) ??
        device.device_subtype}
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
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/devices')}>
          {tDevice('detail.backToList')}
        </Button>
        <Space>
          <Dropdown
            menu={{ items: statusMenuItems, onClick: ({ key }) => handleStatusChange(Number(key)) }}
          >
            <Button icon={<SwapOutlined />}>{tDevice('detail.changeStatus')}</Button>
          </Dropdown>
          {hasSsh && (
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshDeviceInfo}
              loading={syncSwitchInfo.isPending}
            >
              {tDevice('detail.refreshInfo')}
            </Button>
          )}
          <Button type="primary" icon={<EditOutlined />} onClick={() => form.open()}>
            {tCommon('action.edit')}
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            {tCommon('action.delete')}
          </Button>
        </Space>
      </div>

      {/* 设备概要 */}
      <Descriptions column={{ xs: 1, md: 3 }} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label={tDevice('field.name')}>
          <strong style={{ fontSize: 16 }}>{device.device_name}</strong>
        </Descriptions.Item>
        <Descriptions.Item label={tCommon('field.type')}>
          <Space>
            <Tag>
              {getDeviceTypeMeta(device.device_type as DeviceType, tDevice)?.label ??
                device.device_type}
            </Tag>
            {subtypeTag}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={tCommon('field.status')}>
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? tDevice('status.unknown')}</Tag>
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

      {/* 编辑表单 */}
      <DeviceForm
        open={form.isOpen}
        editRecord={device}
        onClose={() => {
          form.close();
          refetch();
        }}
      />
    </div>
  );
}

export default DeviceDetail;
