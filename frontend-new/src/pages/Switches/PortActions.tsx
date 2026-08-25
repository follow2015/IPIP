/**
 * 交换机端口操作按钮组（容器 / 编排层）
 *
 * 职责：
 * - 渲染端口操作按钮组（详情 / 分配 / 开启关闭 / 限速 / VLAN / 汇聚 / IP / 删除）
 * - 用单一 activeModal 状态机管理 6 个弹窗的开合
 * - 持有副作用逻辑（SSH 提交、确认弹窗、端口配置获取/清除）
 *
 * 弹窗 UI 已拆为独立子组件（同目录 *Modal.tsx），本文件不再内联大段 Modal JSX。
 */
import { confirm } from '@/utils/confirm';
import { useState, useCallback, useRef } from 'react';
import { Button, Space, Modal, Tooltip } from 'antd';
import {
  EyeOutlined,
  UserOutlined,
  CheckOutlined,
  StopOutlined,
  DashboardOutlined,
  TagOutlined,
  ApartmentOutlined,
  DeleteOutlined,
  CopyOutlined
} from '@ant-design/icons';
import {
  useUpdatePortCustomer,
  useSwitchPortDetail,
  useFetchPortConfig,
  useRefreshPortConfig
} from '@/services/switch';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';
import { isAdminDown, extractErrorMessage } from '@/utils/portStatus';
import type { SwitchPort, SwitchPortIP, PortConfigResult } from '@/types/models';
import type { SubmitActionFn } from '@/types/port';
import { PortDetailModal } from './PortDetailModal';
import { AssignCustomerModal, type AssignCustomerValues } from './AssignCustomerModal';
import { SpeedLimitModal, type SpeedLimitValues } from './SpeedLimitModal';
import { VlanConfigModal, type VlanConfigValues } from './VlanConfigModal';
import { TrunkModal, type TrunkValues } from './TrunkModal';
import { IpConfigModal, type IpConfigValues } from './IpConfigModal';

export type { SubmitActionFn } from '@/types/port';

interface PortActionsProps {
  switchId: number;
  port: SwitchPort;
  onRefresh?: () => void;
  submitAction: SubmitActionFn;
  hasSsh?: boolean;
}

type ModalKey = 'detail' | 'assign' | 'speed' | 'vlan' | 'trunk' | 'ip';

const VLAN_IF_RE = /^(?:vlan|vlanif|vlan-interface)\d+$/i;
const TRUNK_IF_RE = /^(?:eth-trunk|bridge-aggregation|port-channel|link-aggregation)\d+$/i;
const LOOPBACK_RE = /^LoopBack\d+$/i;
const METH_RE = /^MEth\d+$/i;
const NULL_RE = /^NULL0$/i;

const extractInterfaceId = (name: string): number | null => {
  const m = name.match(/\d+$/);
  return m ? Number(m[0]) : null;
};

function PortActions({ switchId, port, submitAction, hasSsh = true }: PortActionsProps) {
  const updatePortCustomer = useUpdatePortCustomer();
  const fetchPortConfig = useFetchPortConfig();
  const refreshPortConfig = useRefreshPortConfig();
  const msg = useMessage();
  const msgRef = useRef(msg);
  msgRef.current = msg;
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const portName = port.port_name;

  const [activeModal, setActiveModal] = useState<ModalKey | null>(null);
  const openModal = (key: ModalKey) => setActiveModal(key);
  const closeModal = () => setActiveModal(null);

  const [portConfig, setPortConfig] = useState<PortConfigResult | null>(null);

  const { data: portDetail, isLoading: loadingDetail } = useSwitchPortDetail(
    switchId,
    portName,
    activeModal === 'detail' || activeModal === 'ip'
  );

  const portType = NULL_RE.test(portName)
    ? 'null'
    : VLAN_IF_RE.test(portName)
      ? 'vlan'
      : TRUNK_IF_RE.test(portName)
        ? 'trunk'
        : LOOPBACK_RE.test(portName)
          ? 'loopback'
          : METH_RE.test(portName)
            ? 'meth'
            : 'normal';


  const handleTogglePort = (action: 'enable' | 'disable') => {
    const isEnable = action === 'enable';
    confirm({
      title: `确认${isEnable ? '开启' : '关闭'}端口`,
      content: `确定要${isEnable ? '开启' : '关闭'}端口 ${portName} 吗？将通过SSH执行操作。`,
      onOk: () => {
        submitAction(isEnable ? 'enable_port' : 'disable_port', portName);
      }
    });
  };


  const handleAssignSubmit = async (values: AssignCustomerValues) => {
    try {
      const rawCustomerId = values.customer_id;
      const customerId = rawCustomerId === 0 || rawCustomerId == null ? null : rawCustomerId;
      const description = values.description ?? '';
      closeModal();

      if (customerId !== (port.customer_id ?? null)) {
        updatePortCustomer
          .mutateAsync({ switchId, port: portName, data: { customer_id: customerId } })
          .catch((err) => msg.error(extractErrorMessage(err)));
      }

      if (description !== (port.notes ?? '')) {
        submitAction('update_port_info', portName, { description });
      }
    } catch (err) {
      msg.error(extractErrorMessage(err));
    }
  };


  const maxSpeed = port.max_speed ?? 10000;

  const handleSpeedSubmit = async (values: SpeedLimitValues) => {
    try {
      const inbound = Number(values.inbound);
      const outbound = Number(values.outbound);
      if (inbound < 0 || outbound < 0) {
        msg.error('限速值不能为负数');
        return;
      }
      closeModal();
      submitAction('set_port_speed', portName, {
        inbound_speed: inbound,
        outbound_speed: outbound
      });
    } catch (err) {
      msg.error(extractErrorMessage(err));
    }
  };


  const handleVlanSubmit = async (values: VlanConfigValues) => {
    try {
      const vlanId = Number(values.vlan_id);
      if (vlanId < 1 || vlanId > 4094) {
        msg.error('VLAN ID 范围：1-4094');
        return;
      }
      closeModal();
      submitAction('set_port_vlan', portName, {
        vlan_id: vlanId,
        mode: values.mode,
        allowed_vlans:
          values.mode === 'trunk' && values.allowed_vlans ? values.allowed_vlans.trim() : null
      });
    } catch (err) {
      msg.error(extractErrorMessage(err));
    }
  };


  const handleTrunkSubmit = async (values: TrunkValues) => {
    try {
      const trunkId = Number(values.trunk_id);
      if (isNaN(trunkId) || trunkId < 0) {
        msg.error('Trunk ID 必须为非负整数');
        return;
      }
      closeModal();
      submitAction('add_port_to_trunk', portName, { channel_id: trunkId });
    } catch (err) {
      msg.error(extractErrorMessage(err));
    }
  };


  const handleIPSubmit = async (values: IpConfigValues) => {
    try {
      closeModal();
      submitAction('set_port_ip', portName, {
        ip_address: values.ip_address.trim(),
        subnet_mask: values.subnet_mask,
        is_secondary: values.ip_type === 'secondary'
      });
    } catch (err) {
      msg.error(extractErrorMessage(err));
    }
  };


  const handleDeleteIP = (ipAddress: string, subnetMask: string, isSecondary: boolean = false) => {
    if (!portDetail) {
      msg.warning('端口详情未加载，请稍候再试');
      return;
    }
    if (!isSecondary && portDetail.ip_list && portDetail.ip_list.length > 1) {
      Modal.warning({
        title: '无法删除主IP',
        content: '该端口存在多个IP地址，请先删除所有从IP后再删除主IP。'
      });
      return;
    }
    confirm({
      title: '确认删除IP',
      content: `确定删除端口 "${portName}" 的 IP 地址 ${ipAddress}/${subnetMask}？`,
      onOk: () => {
        submitAction('delete_port_ip', portName, {
          ip_address: ipAddress,
          subnet_mask: subnetMask,
          is_secondary: isSecondary
        });
      }
    });
  };


  const handleGetConfig = useCallback(
    async (forceRefresh = false) => {
      try {
        const mutation = forceRefresh ? refreshPortConfig : fetchPortConfig;
        const result = await mutation.mutateAsync({ switchId, port: portName });
        const data = result?.data;
        if (data) {
          setPortConfig(data);
          msgRef.current.success(
            forceRefresh
              ? '配置已刷新并同步'
              : data.from_cache
                ? '已从缓存加载配置'
                : '已从设备获取配置并同步'
          );
        }
      } catch (err) {
        msgRef.current.error(extractErrorMessage(err));
      }
    },
    [fetchPortConfig, refreshPortConfig, switchId, portName]
  );


  const handleClearConfig = () => {
    confirm({
      title: '确认清除端口配置',
      content: `确定清除端口 "${portName}" 的设备配置？该端口配置将还原为初始状态。此操作不可逆！`,
      okText: '确认清除',
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('clear_port_config', portName);
      }
    });
  };


  const handleDeleteVlanIf = () => {
    const vlanId = extractInterfaceId(portName);
    if (!vlanId) {
      msg.error('无法解析VLAN ID');
      return;
    }
    confirm({
      title: '确认删除VLAN接口',
      content: `确定删除 VLAN 接口 "${portName}"（VLAN ${vlanId}）？该操作将删除对应的VLAN配置及VLANIF接口，不可恢复！`,
      okText: '确认删除',
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('delete_vlan', portName, { vlan_id: vlanId });
      }
    });
  };


  const handleDeleteTrunkIf = () => {
    const trunkId = extractInterfaceId(portName);
    if (!trunkId) {
      msg.error('无法解析Trunk ID');
      return;
    }
    confirm({
      title: '确认删除链路聚合接口',
      content: `确定删除 Eth-Trunk 接口 "${portName}"（Trunk ${trunkId}）？该操作将删除对应的链路聚合组及所有成员端口配置，不可恢复！`,
      okText: '确认删除',
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('delete_trunk', portName, { trunk_id: trunkId });
      }
    });
  };


  const handleDeleteInterface = () => {
    confirm({
      title: '确认删除接口',
      content: `确定删除接口 "${portName}"？该操作不可恢复！`,
      okText: '确认删除',
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('delete_interface', portName);
      }
    });
  };

  return (
    <>
      <Space size={0} wrap>
        {/* NULL0 不显示任何操作 */}
        {portType !== 'null' && (
          <>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => openModal('detail')}
            >
              详情
            </Button>
            <Button
              type="link"
              size="small"
              icon={<UserOutlined />}
              onClick={() => openModal('assign')}
            >
              分配
            </Button>
            {isAdminDown(port.link_status) ? (
              <Button
                type="link"
                size="small"
                icon={<CheckOutlined />}
                onClick={() => handleTogglePort('enable')}
              >
                开启
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                danger
                icon={<StopOutlined />}
                onClick={() => handleTogglePort('disable')}
              >
                关闭
              </Button>
            )}
            {portType !== 'loopback' && portType !== 'meth' && (
              <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
                <Button
                  type="link"
                  size="small"
                  icon={<DashboardOutlined />}
                  onClick={() => openModal('speed')}
                  disabled={!hasSsh}
                >
                  限速
                </Button>
              </Tooltip>
            )}
            {(portType === 'normal' || portType === 'trunk') && (
              <Button
                type="link"
                size="small"
                icon={<TagOutlined />}
                onClick={() => openModal('vlan')}
              >
                VLAN
              </Button>
            )}
            {portType === 'normal' && (
              <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
                <Button
                  type="link"
                  size="small"
                  icon={<ApartmentOutlined />}
                  onClick={() => openModal('trunk')}
                  disabled={!hasSsh}
                >
                  汇聚
                </Button>
              </Tooltip>
            )}
            <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
              <Button
                type="link"
                size="small"
                icon={<CopyOutlined />}
                disabled={!hasSsh}
                onClick={() => {
                  if (portDetail?.eth_trunk_id) {
                    msg.warning(
                      `端口属于 Eth-Trunk ${portDetail.eth_trunk_id}，不能直接配置 IP。请在 Eth-Trunk ${portDetail.eth_trunk_id} 端口上配置。`
                    );
                    return;
                  }
                  const currentVlan = portDetail?.vlan ?? port.vlan;
                  if (currentVlan != null && Number(currentVlan) !== 1) {
                    msg.warning(
                      `端口属于 VLAN ${currentVlan}，不能直接配置 IP。请先去端口详情页清除配置。`
                    );
                    return;
                  }
                  openModal('ip');
                }}
              >
                IP
              </Button>
            </Tooltip>
            {portType === 'vlan' && (
              <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteVlanIf}
                  disabled={!hasSsh}
                >
                  删除
                </Button>
              </Tooltip>
            )}
            {portType === 'trunk' && (
              <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteTrunkIf}
                  disabled={!hasSsh}
                >
                  删除
                </Button>
              </Tooltip>
            )}
            {portType === 'loopback' && (
              <Tooltip title={!hasSsh ? '需SSH连接设备，非网管设备不支持' : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteInterface}
                  disabled={!hasSsh}
                >
                  删除
                </Button>
              </Tooltip>
            )}
          </>
        )}
      </Space>

      <PortDetailModal
        open={activeModal === 'detail'}
        onClose={closeModal}
        portName={portName}
        port={port}
        portDetail={portDetail}
        loadingDetail={loadingDetail}
        portConfig={portConfig}
        portType={portType}
        onGetConfig={handleGetConfig}
        getConfigPending={fetchPortConfig.isPending}
        refreshConfigPending={refreshPortConfig.isPending}
        onClearConfig={handleClearConfig}
        onDeleteIP={handleDeleteIP}
      />

      <AssignCustomerModal
        open={activeModal === 'assign'}
        onClose={closeModal}
        portName={portName}
        initialCustomerId={port.customer_id ?? null}
        initialDescription={port.notes ?? ''}
        customerOptions={customerOptions}
        onSubmit={handleAssignSubmit}
      />

      <SpeedLimitModal
        open={activeModal === 'speed'}
        onClose={closeModal}
        portName={portName}
        maxSpeed={maxSpeed}
        onSubmit={handleSpeedSubmit}
      />

      <VlanConfigModal
        open={activeModal === 'vlan'}
        onClose={closeModal}
        portName={portName}
        portType={portType}
        initialVlanId={port.vlan ?? undefined}
        onSubmit={handleVlanSubmit}
      />

      <TrunkModal
        open={activeModal === 'trunk'}
        onClose={closeModal}
        portName={portName}
        onSubmit={handleTrunkSubmit}
      />

      <IpConfigModal
        open={activeModal === 'ip'}
        onClose={closeModal}
        portName={portName}
        currentIpList={portDetail?.ip_list ?? (port.ip_list as SwitchPortIP[] | null) ?? undefined}
        hasPrimary={(portDetail?.ip_list ?? port.ip_list)?.some((ip) => ip.is_primary) ?? false}
        onSubmit={handleIPSubmit}
      />
    </>
  );
}

export default PortActions;
