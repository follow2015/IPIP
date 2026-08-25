import { confirm } from '@/utils/confirm';
import { useState } from 'react';
import {
  Button,
  Space,
  Tooltip,
  Alert,
  Dropdown,
  Form,
  InputNumber,
  Input,
  Select,
  Modal,
  Checkbox
} from 'antd';
import {
  CheckCircleOutlined,
  StopOutlined,
  EditOutlined,
  ApartmentOutlined,
  DisconnectOutlined,
  UndoOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useBatchPortAction, type BatchPortActionRequest } from '@/services/switch';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';

interface BatchPortActionsProps {
  switchId: number;
  selectedPorts: string[];
  onClearSelection: () => void;
  onRefresh?: () => void;
  hasSsh?: boolean;
  onBatchLocalUpdate?: (portNames: string[], updates: Record<string, unknown>) => Promise<void>;
}

interface BatchActionDef {
  key: string;
  label: string;
  icon: React.ReactNode;
  needParams: boolean;
  sshOnly: boolean;
  disabled?: boolean;
}

const BATCH_ACTIONS: BatchActionDef[] = [
  {
    key: 'enable_port',
    label: '批量启用',
    icon: <CheckCircleOutlined />,
    needParams: false,
    sshOnly: false
  },
  {
    key: 'disable_port',
    label: '批量禁用',
    icon: <StopOutlined />,
    needParams: false,
    sshOnly: false
  },
  {
    key: 'set_port_vlan',
    label: '批量配置VLAN',
    icon: <ApartmentOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'update_port_info',
    label: '批量修改描述',
    icon: <EditOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'assign_customer',
    label: '批量分配客户',
    icon: <TeamOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'add_port_to_trunk',
    label: '批量加入链路聚合',
    icon: <ApartmentOutlined />,
    needParams: true,
    sshOnly: true
  },
  {
    key: 'remove_port_from_channel',
    label: '批量退出链路聚合',
    icon: <DisconnectOutlined />,
    needParams: false,
    sshOnly: true
  },
  {
    key: 'clear_port_config',
    label: '批量恢复默认',
    icon: <UndoOutlined />,
    needParams: false,
    sshOnly: true
  },
  {
    key: 'set_port_speed',
    label: '批量限速',
    icon: <ThunderboltOutlined />,
    needParams: true,
    sshOnly: true
  },
  {
    key: 'cancel_port_speed',
    label: '批量取消限速',
    icon: <CloseCircleOutlined />,
    needParams: true,
    sshOnly: true
  }
];

export default function BatchPortActions({
  switchId,
  selectedPorts,
  onClearSelection,
  onRefresh,
  hasSsh = true,
  onBatchLocalUpdate
}: BatchPortActionsProps) {
  const message = useMessage();
  const batchAction = useBatchPortAction();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const [localLoading, setLocalLoading] = useState(false);
  const [vlanModalOpen, setVlanModalOpen] = useState(false);
  const [descModalOpen, setDescModalOpen] = useState(false);
  const [trunkModalOpen, setTrunkModalOpen] = useState(false);
  const [customerModalOpen, setCustomerModalOpen] = useState(false);
  const [speedModalOpen, setSpeedModalOpen] = useState(false);
  const [cancelSpeedModalOpen, setCancelSpeedModalOpen] = useState(false);
  const [cancelSpeedForm] = Form.useForm();
  const [vlanForm] = Form.useForm();
  const [descForm] = Form.useForm();
  const [trunkForm] = Form.useForm();
  const [customerForm] = Form.useForm();
  const [speedForm] = Form.useForm();

  const availableActions = hasSsh
    ? BATCH_ACTIONS
    : BATCH_ACTIONS.map((a) => ({ ...a, disabled: a.sshOnly }));

  const submitBatchAction = (action: string, params?: Record<string, unknown>) => {
    const data: BatchPortActionRequest = {
      action,
      ports: selectedPorts,
      params
    };

    batchAction.mutate(
      { switchId, data },
      {
        onSuccess: () => {
          message.info('批量操作已提交，完成后将通过消息通知您');
          onClearSelection();
        },
        onError: (err) => {
          message.error('批量操作提交失败：' + String(err));
        }
      }
    );
  };

  const submitLocalBatchAction = async (updates: Record<string, unknown>) => {
    if (!onBatchLocalUpdate) return;
    setLocalLoading(true);
    try {
      await onBatchLocalUpdate(selectedPorts, updates);
      onClearSelection();
      onRefresh?.();
    } catch (err) {
      message.error('批量操作失败：' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setLocalLoading(false);
    }
  };

  const handleSimpleAction = (actionKey: string) => {
    const actionLabel = BATCH_ACTIONS.find((a) => a.key === actionKey)?.label;
    if (hasSsh) {
      confirm({
        title: '确认批量操作',
        content: `确定要对 ${selectedPorts.length} 个端口执行"${actionLabel}"吗？`,
        onOk: () => submitBatchAction(actionKey)
      });
    } else {
      const updates: Record<string, unknown> = {};
      if (actionKey === 'enable_port') {
        updates.usage_status = 'free';
      } else if (actionKey === 'disable_port') {
        updates.usage_status = 'disabled';
      }
      confirm({
        title: '确认批量操作',
        content: `确定要对 ${selectedPorts.length} 个端口执行"${actionLabel}"吗？`,
        onOk: () => submitLocalBatchAction(updates)
      });
    }
  };

  const handleVlanOk = () => {
    vlanForm.validateFields().then((values) => {
      if (hasSsh) {
        submitBatchAction('set_port_vlan', {
          vlan_id: values.vlan_id,
          mode: values.mode || 'access',
          allowed_vlans: values.allowed_vlans || undefined
        });
      } else {
        submitLocalBatchAction({ vlan: String(values.vlan_id) });
      }
      setVlanModalOpen(false);
      vlanForm.resetFields();
    });
  };

  const handleDescOk = () => {
    descForm.validateFields().then((values) => {
      if (hasSsh) {
        submitBatchAction('update_port_info', {
          description: values.description || ''
        });
      } else {
        submitLocalBatchAction({ description: values.description || '' });
      }
      setDescModalOpen(false);
      descForm.resetFields();
    });
  };

  const handleTrunkOk = () => {
    trunkForm.validateFields().then((values) => {
      submitBatchAction('add_port_to_trunk', {
        channel_id: values.channel_id
      });
      setTrunkModalOpen(false);
      trunkForm.resetFields();
    });
  };

  const handleCustomerOk = () => {
    customerForm.validateFields().then((values) => {
      if (hasSsh) {
        submitBatchAction('assign_customer', {
          customer_id: values.customer_id
        });
      } else {
        submitLocalBatchAction({ customer_id: values.customer_id ?? null });
      }
      setCustomerModalOpen(false);
      customerForm.resetFields();
    });
  };

  const handleSpeedOk = () => {
    speedForm.validateFields().then((values) => {
      const params: Record<string, unknown> = {};
      if (values.inbound != null && values.inbound > 0) {
        params.inbound = values.inbound;
      }
      if (values.outbound != null && values.outbound > 0) {
        params.outbound = values.outbound;
      }
      if (Object.keys(params).length === 0) {
        message.warning('请至少填写一个大于 0 的限速值（入向/出向）');
        return;
      }
      submitBatchAction('set_port_speed', params);
      setSpeedModalOpen(false);
      speedForm.resetFields();
    });
  };

  const handleCancelSpeedOk = () => {
    cancelSpeedForm.validateFields().then((values) => {
      const cancelInbound = values.cancel_inbound ?? false;
      const cancelOutbound = values.cancel_outbound ?? false;
      if (!cancelInbound && !cancelOutbound) {
        message.warning('请至少勾选一个要取消的方向（入向/出向）');
        return;
      }
      const params: Record<string, unknown> = {
        cancel_inbound: cancelInbound,
        cancel_outbound: cancelOutbound
      };
      submitBatchAction('cancel_port_speed', params);
      setCancelSpeedModalOpen(false);
      cancelSpeedForm.resetFields();
    });
  };

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    switch (key) {
      case 'enable_port':
      case 'disable_port':
      case 'remove_port_from_channel':
      case 'clear_port_config':
        handleSimpleAction(key);
        break;
      case 'set_port_vlan':
        setVlanModalOpen(true);
        break;
      case 'update_port_info':
        setDescModalOpen(true);
        break;
      case 'assign_customer':
        setCustomerModalOpen(true);
        break;
      case 'add_port_to_trunk':
        setTrunkModalOpen(true);
        break;
      case 'set_port_speed':
        setSpeedModalOpen(true);
        break;
      case 'cancel_port_speed':
        setCancelSpeedModalOpen(true);
        break;
    }
  };

  const menuItems: MenuProps['items'] = availableActions.map((action) => ({
    key: action.key,
    label: action.disabled ? (
      <Tooltip title="需SSH连接设备，非网管设备不支持">
        <span style={{ color: 'rgba(0,0,0,0.25)' }}>{action.label}</span>
      </Tooltip>
    ) : (
      action.label
    ),
    icon: action.icon,
    disabled: action.disabled
  }));

  if (selectedPorts.length === 0) return null;

  const isOperating = batchAction.isPending || localLoading;

  return (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={
          <Space>
            <span>
              已选择 <strong>{selectedPorts.length}</strong> 个端口
            </span>
            <Dropdown menu={{ items: menuItems, onClick: handleMenuClick }} trigger={['click']}>
              <Button size="small" type="primary" loading={isOperating}>
                批量操作
              </Button>
            </Dropdown>
            <Button size="small" type="link" onClick={onClearSelection}>
              取消选择
            </Button>
          </Space>
        }
      />

      {/* VLAN 配置弹窗 */}
      <Modal
        title="批量配置VLAN"
        open={vlanModalOpen}
        onOk={handleVlanOk}
        onCancel={() => {
          setVlanModalOpen(false);
          vlanForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={vlanForm} layout="vertical" initialValues={{ mode: 'access' }}>
          <Form.Item
            name="vlan_id"
            label="VLAN ID"
            rules={[{ required: true, message: '请输入VLAN ID' }]}
          >
            <InputNumber min={1} max={4094} placeholder="如 100" style={{ width: '100%' }} />
          </Form.Item>
          {hasSsh && (
            <>
              <Form.Item name="mode" label="模式">
                <Select
                  options={[
                    { value: 'access', label: 'Access' },
                    { value: 'trunk', label: 'Trunk' }
                  ]}
                />
              </Form.Item>
              <Form.Item noStyle shouldUpdate={(prev, cur) => prev.mode !== cur.mode}>
                {({ getFieldValue }) =>
                  getFieldValue('mode') === 'trunk' ? (
                    <Form.Item name="allowed_vlans" label="允许的VLAN（如 200-210,300）">
                      <Input placeholder="如 200-210,300" />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>

      {/* 描述修改弹窗 */}
      <Modal
        title="批量修改端口描述"
        open={descModalOpen}
        onOk={handleDescOk}
        onCancel={() => {
          setDescModalOpen(false);
          descForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={descForm} layout="vertical">
          <Form.Item name="description" label="端口描述">
            <Input.TextArea rows={3} placeholder="输入新的端口描述（留空则清除描述）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 链路聚合弹窗（仅 SSH 模式） */}
      {hasSsh && (
        <Modal
          title="批量加入链路聚合"
          open={trunkModalOpen}
          onOk={handleTrunkOk}
          onCancel={() => {
            setTrunkModalOpen(false);
            trunkForm.resetFields();
          }}
          destroyOnHidden
        >
          <Form form={trunkForm} layout="vertical">
            <Form.Item
              name="channel_id"
              label="Eth-Trunk ID"
              rules={[{ required: true, message: '请输入Eth-Trunk ID' }]}
            >
              <InputNumber min={1} max={512} placeholder="如 10" style={{ width: '100%' }} />
            </Form.Item>
          </Form>
        </Modal>
      )}

      {/* 客户分配弹窗 */}
      <Modal
        title="批量分配客户"
        open={customerModalOpen}
        onOk={handleCustomerOk}
        onCancel={() => {
          setCustomerModalOpen(false);
          customerForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={customerForm} layout="vertical">
          <Form.Item name="customer_id" label="选择客户">
            <Select
              allowClear
              showSearch
              placeholder="选择要分配的客户（留空则清除客户）"
              options={customerOptions ?? []}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 批量限速弹窗（仅 SSH 模式） */}
      {hasSsh && (
        <Modal
          title="批量限速"
          open={speedModalOpen}
          onOk={handleSpeedOk}
          onCancel={() => {
            setSpeedModalOpen(false);
            speedForm.resetFields();
          }}
          destroyOnHidden
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="限速策略按「方向 + 限速值」共享：相同限速值的端口复用同一份策略，不在设备上重复生成。"
          />
          <Form form={speedForm} layout="vertical">
            <Form.Item name="inbound" label="入向限速 (Mbps)" extra="上行限速，留空表示不设置">
              <InputNumber min={1} max={1000000} placeholder="如 1000" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="outbound" label="出向限速 (Mbps)" extra="下行限速，留空表示不设置">
              <InputNumber min={1} max={1000000} placeholder="如 1200" style={{ width: '100%' }} />
            </Form.Item>
          </Form>
        </Modal>
      )}

      {/* 批量取消限速弹窗（仅 SSH 模式） */}
      {hasSsh && (
        <Modal
          title="批量取消限速"
          open={cancelSpeedModalOpen}
          onOk={handleCancelSpeedOk}
          onCancel={() => {
            setCancelSpeedModalOpen(false);
            cancelSpeedForm.resetFields();
          }}
          destroyOnHidden
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="取消限速会按方向逐端口撤销交换机上已应用的限速策略引用（华为CE需带策略名撤销）。未应用限速的端口会自动跳过。"
          />
          <Form
            form={cancelSpeedForm}
            layout="vertical"
            initialValues={{ cancel_inbound: true, cancel_outbound: true }}
          >
            <Form.Item name="cancel_inbound" valuePropName="checked">
              <Checkbox>取消入向限速（上行）</Checkbox>
            </Form.Item>
            <Form.Item name="cancel_outbound" valuePropName="checked">
              <Checkbox>取消出向限速（下行）</Checkbox>
            </Form.Item>
          </Form>
        </Modal>
      )}
    </>
  );
}
