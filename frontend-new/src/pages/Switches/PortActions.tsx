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
import { useConfirm } from '@/utils/confirm';
import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const updatePortCustomer = useUpdatePortCustomer();
  const fetchPortConfig = useFetchPortConfig();
  const refreshPortConfig = useRefreshPortConfig();
  const msg = useMessage();
  const msgRef = useRef(msg);
  msgRef.current = msg;
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const portName = port.port_name;
  const sshOnlyTip = td('switch.batch.sshOnlyTip');

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
      title: isEnable ? td('switch.port.enableTitle') : td('switch.port.disableTitle'),
      content: isEnable
        ? td('switch.port.enableContent', { name: portName })
        : td('switch.port.disableContent', { name: portName }),
      okText: tc('action.ok'),
      cancelText: tc('action.cancel'),
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
          .catch((err) => msg.error(extractErrorMessage(err, tc)));
      }

      if (description !== (port.notes ?? '')) {
        submitAction('update_port_info', portName, { description });
      }
    } catch (err) {
      msg.error(extractErrorMessage(err, tc));
    }
  };


  const maxSpeed = port.max_speed ?? 10000;

  const handleSpeedSubmit = async (values: SpeedLimitValues) => {
    try {
      const inbound = Number(values.inbound);
      const outbound = Number(values.outbound);
      if (inbound < 0 || outbound < 0) {
        msg.error(td('switch.port.speedNegative'));
        return;
      }
      closeModal();
      submitAction('set_port_speed', portName, {
        inbound_speed: inbound,
        outbound_speed: outbound
      });
    } catch (err) {
      msg.error(extractErrorMessage(err, tc));
    }
  };


  const handleVlanSubmit = async (values: VlanConfigValues) => {
    try {
      const vlanId = Number(values.vlan_id);
      if (vlanId < 1 || vlanId > 4094) {
        msg.error(td('switch.port.vlanRange'));
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
      msg.error(extractErrorMessage(err, tc));
    }
  };


  const handleTrunkSubmit = async (values: TrunkValues) => {
    try {
      const trunkId = Number(values.trunk_id);
      if (isNaN(trunkId) || trunkId < 0) {
        msg.error(td('switch.port.trunkIdInvalid'));
        return;
      }
      closeModal();
      submitAction('add_port_to_trunk', portName, { channel_id: trunkId });
    } catch (err) {
      msg.error(extractErrorMessage(err, tc));
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
      msg.error(extractErrorMessage(err, tc));
    }
  };


  const handleDeleteIP = (ipAddress: string, subnetMask: string, isSecondary: boolean = false) => {
    if (!portDetail) {
      msg.warning(td('switch.port.detailNotLoaded'));
      return;
    }
    if (!isSecondary && portDetail.ip_list && portDetail.ip_list.length > 1) {
      Modal.warning({
        title: td('switch.port.cannotDeletePrimaryIp'),
        content: td('switch.port.cannotDeletePrimaryIpContent')
      });
      return;
    }
    confirm({
      title: td('switch.port.deleteIpTitle'),
      content: td('switch.port.deleteIpContent', {
        name: portName,
        ip: ipAddress,
        mask: subnetMask
      }),
      okText: tc('action.delete'),
      cancelText: tc('action.cancel'),
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
              ? td('switch.port.configRefreshed')
              : data.from_cache
                ? td('switch.port.configFromCache')
                : td('switch.port.configFetched')
          );
        }
      } catch (err) {
        msgRef.current.error(extractErrorMessage(err, tc));
      }
    },
    [fetchPortConfig, refreshPortConfig, switchId, portName, td, tc]
  );


  const handleClearConfig = () => {
    confirm({
      title: td('switch.port.clearConfigTitle'),
      content: td('switch.port.clearConfigContent', { name: portName }),
      okText: td('switch.port.clearConfigOk'),
      cancelText: tc('action.cancel'),
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('clear_port_config', portName);
      }
    });
  };


  const handleDeleteVlanIf = () => {
    const vlanId = extractInterfaceId(portName);
    if (!vlanId) {
      msg.error(td('switch.port.vlanIdUnparsable'));
      return;
    }
    confirm({
      title: td('switch.port.deleteVlanIfTitle'),
      content: td('switch.port.deleteVlanIfContent', { name: portName, vlanId }),
      okText: tc('action.delete'),
      cancelText: tc('action.cancel'),
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('delete_vlan', portName, { vlan_id: vlanId });
      }
    });
  };


  const handleDeleteTrunkIf = () => {
    const trunkId = extractInterfaceId(portName);
    if (!trunkId) {
      msg.error(td('switch.port.trunkIdUnparsable'));
      return;
    }
    confirm({
      title: td('switch.port.deleteTrunkIfTitle'),
      content: td('switch.port.deleteTrunkIfContent', { name: portName, trunkId }),
      okText: tc('action.delete'),
      cancelText: tc('action.cancel'),
      okButtonProps: { danger: true },
      onOk: () => {
        submitAction('delete_trunk', portName, { trunk_id: trunkId });
      }
    });
  };


  const handleDeleteInterface = () => {
    confirm({
      title: td('switch.port.deleteInterfaceTitle'),
      content: td('switch.port.deleteInterfaceContent', { name: portName }),
      okText: tc('action.delete'),
      cancelText: tc('action.cancel'),
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
              {tc('action.detail')}
            </Button>
            <Button
              type="link"
              size="small"
              icon={<UserOutlined />}
              onClick={() => openModal('assign')}
            >
              {td('switch.port.assign')}
            </Button>
            {isAdminDown(port.link_status) ? (
              <Button
                type="link"
                size="small"
                icon={<CheckOutlined />}
                onClick={() => handleTogglePort('enable')}
              >
                {td('switch.port.enable')}
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                danger
                icon={<StopOutlined />}
                onClick={() => handleTogglePort('disable')}
              >
                {td('switch.port.disable')}
              </Button>
            )}
            {portType !== 'loopback' && portType !== 'meth' && (
              <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
                <Button
                  type="link"
                  size="small"
                  icon={<DashboardOutlined />}
                  onClick={() => openModal('speed')}
                  disabled={!hasSsh}
                >
                  {td('switch.port.speedLimit')}
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
              <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
                <Button
                  type="link"
                  size="small"
                  icon={<ApartmentOutlined />}
                  onClick={() => openModal('trunk')}
                  disabled={!hasSsh}
                >
                  {td('switch.port.aggregate')}
                </Button>
              </Tooltip>
            )}
            <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
              <Button
                type="link"
                size="small"
                icon={<CopyOutlined />}
                disabled={!hasSsh}
                onClick={() => {
                  if (portDetail?.eth_trunk_id) {
                    msg.warning(
                      td('switch.port.trunkIpBlocked', { id: portDetail.eth_trunk_id })
                    );
                    return;
                  }
                  const currentVlan = portDetail?.vlan ?? port.vlan;
                  if (currentVlan != null && Number(currentVlan) !== 1) {
                    msg.warning(td('switch.port.vlanIpBlocked', { vlan: currentVlan }));
                    return;
                  }
                  openModal('ip');
                }}
              >
                IP
              </Button>
            </Tooltip>
            {portType === 'vlan' && (
              <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteVlanIf}
                  disabled={!hasSsh}
                >
                  {tc('action.delete')}
                </Button>
              </Tooltip>
            )}
            {portType === 'trunk' && (
              <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteTrunkIf}
                  disabled={!hasSsh}
                >
                  {tc('action.delete')}
                </Button>
              </Tooltip>
            )}
            {portType === 'loopback' && (
              <Tooltip title={!hasSsh ? sshOnlyTip : undefined}>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDeleteInterface}
                  disabled={!hasSsh}
                >
                  {tc('action.delete')}
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
