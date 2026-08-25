import { confirm } from '@/utils/confirm';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Tabs, Spin, Button, Space, Tag, Dropdown, Descriptions, Result } from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
  SwapOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useDeviceSuspenseDetail, useDeleteDevice, useUpdateDeviceStatus } from '@/services/device';
import {
  DEVICE_STATUS_MAP,
  DeviceStatusCode,
  DEVICE_SUBTYPE_LABELS,
  DEVICE_SUBTYPE_COLORS,
  DEVICE_TYPE_MAP,
  DeviceType,
  DeviceSubtype
} from '@/types/enums';
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
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const deviceId = Number(id);

  if (Number.isNaN(deviceId)) {
    return (
      <Result
        status="404"
        title="参数无效"
        subTitle="设备 ID 无效"
        extra={<Button onClick={() => navigate(-1)}>返回</Button>}
      />
    );
  }

  return <DeviceDetailContent deviceId={deviceId} />;
}


function DeviceDetailContent({ deviceId }: { deviceId: number }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { data: device, refetch } = useDeviceSuspenseDetail(deviceId);
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
      title: '刷新设备信息',
      content: '将从设备实时获取型号、版本、序列号等信息，后台执行完成后自动刷新。',
      onOk: async () => {
        try {
          await syncSwitchInfo.mutateAsync(deviceId);
          message.info('刷新设备信息已提交，完成后将通过消息通知您');
        } catch {
          
        }
      }
    });
  };

  
  const [formOpen, setFormOpen] = useState(false);

  if (!device) {
    return <div>设备不存在</div>;
  }

  
  const handleDelete = () => {
    confirm({
      title: '确认删除',
      content: `确定要删除设备「${device.device_name}」吗？`,
      okText: '确定',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(device.id);
          message.success('删除成功');
          navigate('/devices');
        } catch (err) {
          message.error(err instanceof Error ? err.message : '删除失败');
        }
      }
    });
  };

  
  const handleStatusChange = async (newStatus: number) => {
    try {
      await updateStatus.mutateAsync({ id: device.id, status: newStatus });
      message.success('状态已变更');
      refetch();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '状态变更失败');
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
      label: t.label,
      children: renderTab(t.key)
    }));

  const statusInfo = DEVICE_STATUS_MAP[device.status as DeviceStatusCode];

  
  const statusMenuItems = Object.entries(DEVICE_STATUS_MAP)
    .filter(([k]) => Number(k) !== device.status)
    .map(([k, v]) => ({
      key: k,
      label: v.label
    }));

  
  const subtypeTag = device.device_subtype ? (
    <Tag color={DEVICE_SUBTYPE_COLORS[device.device_subtype as DeviceSubtype] ?? 'default'}>
      {DEVICE_SUBTYPE_LABELS[device.device_subtype as DeviceSubtype] ?? device.device_subtype}
    </Tag>
  ) : null;

  return (
    <div>
      {}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/devices')}>
          返回列表
        </Button>
        <Space>
          <Dropdown
            menu={{ items: statusMenuItems, onClick: ({ key }) => handleStatusChange(Number(key)) }}
          >
            <Button icon={<SwapOutlined />}>变更状态</Button>
          </Dropdown>
          {hasSsh && (
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshDeviceInfo}
              loading={syncSwitchInfo.isPending}
            >
              刷新设备信息
            </Button>
          )}
          <Button type="primary" icon={<EditOutlined />} onClick={() => setFormOpen(true)}>
            编辑
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
        </Space>
      </div>

      {}
      <Descriptions column={3} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="设备名称">
          <strong style={{ fontSize: 16 }}>{device.device_name}</strong>
        </Descriptions.Item>
        <Descriptions.Item label="类型">
          <Space>
            <Tag>
              {DEVICE_TYPE_MAP[device.device_type as DeviceType]?.label ?? device.device_type}
            </Tag>
            {subtypeTag}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? '未知'}</Tag>
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

      {}
      <DeviceForm
        open={formOpen}
        editRecord={device}
        onClose={() => {
          setFormOpen(false);
          refetch();
        }}
      />
    </div>
  );
}

export default DeviceDetail;
