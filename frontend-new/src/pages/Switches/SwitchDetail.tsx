import { confirm } from '@/utils/confirm';
import { useState, useEffect, useCallback } from 'react';
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

import {
  DEVICE_STATUS_MAP,
  DeviceStatusCode,
  DEVICE_SUBTYPE_LABELS,
  DEVICE_SUBTYPE_COLORS,
  DEVICE_TYPE_MAP,
  DeviceType,
  DeviceSubtype,
  SWITCH_ROLE_MAP,
  SwitchRoleCode
} from '@/types/enums';
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
  const switchId = Number(id);

  if (Number.isNaN(switchId)) {
    return (
      <Result
        status="404"
        title="参数无效"
        subTitle="交换机 ID 无效"
        extra={<Button onClick={() => navigate(-1)}>返回</Button>}
      />
    );
  }

  return <SwitchDetailContent switchId={switchId} />;
}

function SwitchDetailContent({ switchId }: { switchId: number }) {
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

  const [formOpen, setFormOpen] = useState(false);
  const [deviceFormOpen, setDeviceFormOpen] = useState(false);

  const syncSwitchInfo = useSyncSwitchInfo();
  const handleRefreshDeviceInfo = () => {
    confirm({
      title: '刷新设备信息',
      content: '将从设备实时获取型号、版本、序列号等信息，后台执行完成后自动刷新。',
      onOk: async () => {
        try {
          await syncSwitchInfo.mutateAsync(switchId);
          message.info('刷新设备信息已提交，完成后将通过消息通知您');
        } catch {
          message.error('刷新设备信息提交失败');
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
  if (!device) return <div>设备不存在</div>;

  const handleDelete = () => {
    confirm({
      title: '确认删除',
      content: `确定要删除网络设备「${device.device_name}」吗？将同时删除关联的凭据和端口数据。`,
      okText: '确定',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteDevice.mutateAsync(device.id);
        message.success('删除成功');
        navigate('/switches');
      }
    });
  };

  const handleStatusChange = (newStatus: number) => {
    updateStatus.mutateAsync({ id: device.id, status: newStatus }).then(() => {
      message.success('状态已变更');
      refetch();
    });
  };

  const handleCopyDetail = () => {
    if (!switchData) return;
    const text = [
      '交换机详细信息',
      '==================',
      `名称: ${switchData.name}`,
      `IP地址: ${switchData.ip_address ?? '-'}`,
      `端口: ${switchData.port ?? 22}`,
      `用户名: ${switchData.username ?? '-'}`,
      `协议: ${switchData.protocol ?? 'SSH'}`,
      `设备类型: ${switchData.device_type ?? '-'}`,
      `设备型号: ${switchData.device_model ?? '-'}`,
      `所在机房: ${switchData.room_name ?? '-'}`,
      `设备版本: ${switchData.device_version ?? '-'}`,
      `序列号: ${switchData.device_serial ?? '-'}`,
      `运行时间: ${switchData.device_uptime ?? '-'}`,
      `MAC地址: ${switchData.mac_address?.length ? switchData.mac_address.join(', ') : '-'}`
    ].join('\n');
    navigator.clipboard.writeText(text).then(() => message.success('详情已复制'));
  };

  const tabItems = [];

  tabItems.push({
    key: 'basic',
    label: '基本信息',
    children: (
      <div>
        <BasicTab device={device} />
        {/* 交换机专属信息 */}
        {switchData && (
          <Descriptions
            title="交换机配置"
            column={2}
            bordered
            size="small"
            style={{ marginTop: 16 }}
          >
            <Descriptions.Item label="管理IP">{switchData.ip_address ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="SSH端口">{switchData.port ?? 22}</Descriptions.Item>
            <Descriptions.Item label="协议">{switchData.protocol ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="用户名">{switchData.username ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="设备驱动">{switchData.device_type ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="角色">
              {SWITCH_ROLE_MAP[switchData.switch_role as SwitchRoleCode]?.label ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="层级">
              {switchData.layer != null ? `L${switchData.layer}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="端口数">{switchData.port_num ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="上行设备">
              {switchData.uplink_device_name ??
                (switchData.uplink_device_id ? `ID:${switchData.uplink_device_id}` : '-')}
            </Descriptions.Item>
            <Descriptions.Item label="上行端口">
              {switchData.uplink_port_names?.length ? switchData.uplink_port_names.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="对端互联端口">
              {switchData.peer_port_names?.length ? switchData.peer_port_names.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="核心交换机">
              {switchData.core_device_name ??
                (switchData.core_device_id ? `ID:${switchData.core_device_id}` : '-')}
            </Descriptions.Item>
            <Descriptions.Item label="主机名">{switchData.hostname ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="版本">{switchData.device_version ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="序列号">{switchData.device_serial ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="运行时间">
              {switchData.device_uptime ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="MAC地址">
              {switchData.mac_address?.length ? switchData.mac_address.join(', ') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="管理权限">
              {hasSsh ? <Tag color="green">有SSH权限</Tag> : <Tag>仅记录</Tag>}
            </Descriptions.Item>
          </Descriptions>
        )}
      </div>
    )
  });

  tabItems.push({
    key: 'ports',
    label: '端口',
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
    label: 'VLAN',
    children: <VlanTab deviceId={switchId} hasSsh={hasSsh} />
  });

  tabItems.push({
    key: 'lag',
    label: '链路聚合',
    children: <LagTab deviceId={switchId} hasSsh={hasSsh} />
  });

  tabItems.push({
    key: 'connections',
    label: '连接',
    children: <ConnectionTab device={device} />
  });

  tabItems.push({
    key: 'storage',
    label: '存储',
    children: <StorageTab deviceId={switchId} />
  });

  tabItems.push({
    key: 'asset',
    label: '资产信息',
    children: <AssetTab device={device} />
  });

  tabItems.push({
    key: 'metrics',
    label: '监控数据',
    children: <MetricsTab deviceId={switchId} />
  });

  tabItems.push({
    key: 'credentials',
    label: '监控凭据',
    children: <CredentialTab device={device} />
  });

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
          返回列表
        </Button>
        <Space>
          <Button icon={<CopyOutlined />} onClick={handleCopyDetail}>
            复制详情
          </Button>
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
          {hasSsh && (
            <Button type="primary" icon={<EditOutlined />} onClick={() => setFormOpen(true)}>
              远程信息管理
            </Button>
          )}
          <Button icon={<EditOutlined />} onClick={() => setDeviceFormOpen(true)}>
            编辑
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
        </Space>
      </div>

      {/* 设备概要 */}
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

      {/* 编辑表单（简化版，仅交换机配置） */}
      <SwitchForm
        open={formOpen}
        editRecord={switchData ?? null}
        onClose={() => {
          setFormOpen(false);
          refetch();
        }}
      />

      {/* 完整编辑表单（DeviceForm） */}
      <DeviceForm
        open={deviceFormOpen}
        editRecord={null}
        editDeviceId={device.id}
        onClose={() => {
          setDeviceFormOpen(false);
          refetch();
        }}
      />
    </div>
  );
}

export default SwitchDetail;
