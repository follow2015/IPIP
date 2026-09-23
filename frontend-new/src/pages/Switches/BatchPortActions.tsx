import { useConfirm } from '@/utils/confirm';
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useBatchPortAction, type BatchPortActionRequest } from '@/services/switch';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';
import { extractErrorMessage } from '@/utils/portStatus';

interface BatchPortActionsProps {
  switchId: number;
  selectedPorts: string[];
  onClearSelection: () => void;
  onRefresh?: () => void;
  hasSsh?: boolean;
  onBatchLocalUpdate?: (portNames: string[], updates: Record<string, unknown>) => Promise<void>;
}

type BatchActionKey =
  | 'enable_port'
  | 'disable_port'
  | 'set_port_vlan'
  | 'update_port_info'
  | 'assign_customer'
  | 'add_port_to_trunk'
  | 'remove_port_from_channel'
  | 'clear_port_config'
  | 'set_port_speed'
  | 'cancel_port_speed';

type BatchActionLabelKey =
  | 'switch.batch.enable'
  | 'switch.batch.disable'
  | 'switch.batch.setVlan'
  | 'switch.batch.updateInfo'
  | 'switch.batch.assignCustomer'
  | 'switch.batch.addToTrunk'
  | 'switch.batch.removeFromChannel'
  | 'switch.batch.clearConfig'
  | 'switch.batch.setSpeed'
  | 'switch.batch.cancelSpeed';

interface BatchActionDef {
  key: BatchActionKey;
  labelKey: BatchActionLabelKey;
  icon: React.ReactNode;
  needParams: boolean;
  sshOnly: boolean;
  disabled?: boolean;
}

const BATCH_ACTIONS: BatchActionDef[] = [
  {
    key: 'enable_port',
    labelKey: 'switch.batch.enable',
    icon: <CheckCircleOutlined />,
    needParams: false,
    sshOnly: false
  },
  {
    key: 'disable_port',
    labelKey: 'switch.batch.disable',
    icon: <StopOutlined />,
    needParams: false,
    sshOnly: false
  },
  {
    key: 'set_port_vlan',
    labelKey: 'switch.batch.setVlan',
    icon: <ApartmentOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'update_port_info',
    labelKey: 'switch.batch.updateInfo',
    icon: <EditOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'assign_customer',
    labelKey: 'switch.batch.assignCustomer',
    icon: <TeamOutlined />,
    needParams: true,
    sshOnly: false
  },
  {
    key: 'add_port_to_trunk',
    labelKey: 'switch.batch.addToTrunk',
    icon: <ApartmentOutlined />,
    needParams: true,
    sshOnly: true
  },
  {
    key: 'remove_port_from_channel',
    labelKey: 'switch.batch.removeFromChannel',
    icon: <DisconnectOutlined />,
    needParams: false,
    sshOnly: true
  },
  {
    key: 'clear_port_config',
    labelKey: 'switch.batch.clearConfig',
    icon: <UndoOutlined />,
    needParams: false,
    sshOnly: true
  },
  {
    key: 'set_port_speed',
    labelKey: 'switch.batch.setSpeed',
    icon: <ThunderboltOutlined />,
    needParams: true,
    sshOnly: true
  },
  {
    key: 'cancel_port_speed',
    labelKey: 'switch.batch.cancelSpeed',
    icon: <CloseCircleOutlined />,
    needParams: true,
    sshOnly: true
  }
];

const buildMenuItems = (
  actions: BatchActionDef[],
  td: TFunction<'device'>
): MenuProps['items'] =>
  actions.map((action) => ({
    key: action.key,
    label: action.disabled ? (
      <Tooltip title={td('switch.batch.sshOnlyTip')}>
        <span style={{ color: 'rgba(0,0,0,0.25)' }}>{td(action.labelKey)}</span>
      </Tooltip>
    ) : (
      td(action.labelKey)
    ),
    icon: action.icon,
    disabled: action.disabled
  }));

export default function BatchPortActions({
  switchId,
  selectedPorts,
  onClearSelection,
  onRefresh,
  hasSsh = true,
  onBatchLocalUpdate
}: BatchPortActionsProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const message = useMessage();
  const batchAction = useBatchPortAction();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const [localLoading, setLocalLoading] = useState(false);
  const vlanModal = useDisclosure();
  const descModal = useDisclosure();
  const trunkModal = useDisclosure();
  const customerModal = useDisclosure();
  const speedModal = useDisclosure();
  const cancelSpeedModal = useDisclosure();
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
          message.info(td('switch.batch.submitted'));
          onClearSelection();
        },
        onError: (err) => {
          message.error(td('switch.batch.submitFailed', { error: extractErrorMessage(err, tc) }));
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
      message.error(td('switch.batch.failed', { error: extractErrorMessage(err, tc) }));
    } finally {
      setLocalLoading(false);
    }
  };

  const handleSimpleAction = (actionKey: BatchActionKey) => {
    const actionDef = BATCH_ACTIONS.find((a) => a.key === actionKey);
    const actionLabel = actionDef ? td(actionDef.labelKey) : actionKey;
    const confirmContent = td('switch.batch.confirmContent', {
      count: selectedPorts.length,
      action: actionLabel
    });
    if (hasSsh) {
      confirm({
        title: td('switch.batch.confirmTitle'),
        content: confirmContent,
        okText: tc('action.ok'),
        cancelText: tc('action.cancel'),
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
        title: td('switch.batch.confirmTitle'),
        content: confirmContent,
        okText: tc('action.ok'),
        cancelText: tc('action.cancel'),
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
      vlanModal.close();
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
      descModal.close();
      descForm.resetFields();
    });
  };

  const handleTrunkOk = () => {
    trunkForm.validateFields().then((values) => {
      submitBatchAction('add_port_to_trunk', {
        channel_id: values.channel_id
      });
      trunkModal.close();
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
      customerModal.close();
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
        message.warning(td('switch.batch.warning.speedRequired'));
        return;
      }
      submitBatchAction('set_port_speed', params);
      speedModal.close();
      speedForm.resetFields();
    });
  };

  const handleCancelSpeedOk = () => {
    cancelSpeedForm.validateFields().then((values) => {
      const cancelInbound = values.cancel_inbound ?? false;
      const cancelOutbound = values.cancel_outbound ?? false;
      if (!cancelInbound && !cancelOutbound) {
        message.warning(td('switch.batch.warning.directionRequired'));
        return;
      }
      const params: Record<string, unknown> = {
        cancel_inbound: cancelInbound,
        cancel_outbound: cancelOutbound
      };
      submitBatchAction('cancel_port_speed', params);
      cancelSpeedModal.close();
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
        vlanModal.open();
        break;
      case 'update_port_info':
        descModal.open();
        break;
      case 'assign_customer':
        customerModal.open();
        break;
      case 'add_port_to_trunk':
        trunkModal.open();
        break;
      case 'set_port_speed':
        speedModal.open();
        break;
      case 'cancel_port_speed':
        cancelSpeedModal.open();
        break;
    }
  };

  const menuItems = buildMenuItems(availableActions, td);

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
              {tc('batch.selectedPrefix')} <strong>{selectedPorts.length}</strong>{' '}
              {td('switch.batch.portUnit', { count: selectedPorts.length })}
            </span>
            <Dropdown menu={{ items: menuItems, onClick: handleMenuClick }} trigger={['click']}>
              <Button size="small" type="primary" loading={isOperating}>
                {td('switch.batch.action')}
              </Button>
            </Dropdown>
            <Button size="small" type="link" onClick={onClearSelection}>
              {tc('batch.clear')}
            </Button>
          </Space>
        }
      />

      {/* VLAN 配置弹窗 */}
      <Modal
        title={td('switch.batch.modal.setVlanTitle')}
        open={vlanModal.isOpen}
        onOk={handleVlanOk}
        onCancel={() => {
          vlanModal.close();
          vlanForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={vlanForm} layout="vertical" initialValues={{ mode: 'access' }}>
          <Form.Item
            name="vlan_id"
            label={td('switch.batch.form.vlanId')}
            rules={[{ required: true, message: td('switch.batch.form.vlanIdRequired') }]}
          >
            <InputNumber
              min={1}
              max={4094}
              placeholder={td('switch.batch.form.vlanIdPlaceholder')}
              style={{ width: '100%' }}
            />
          </Form.Item>
          {hasSsh && (
            <>
              <Form.Item name="mode" label={td('switch.batch.form.mode')}>
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
                    <Form.Item
                      name="allowed_vlans"
                      label={td('switch.batch.form.allowedVlans')}
                    >
                      <Input placeholder={td('switch.batch.form.allowedVlansPlaceholder')} />
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
        title={td('switch.batch.modal.descTitle')}
        open={descModal.isOpen}
        onOk={handleDescOk}
        onCancel={() => {
          descModal.close();
          descForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={descForm} layout="vertical">
          <Form.Item name="description" label={td('switch.batch.form.description')}>
            <Input.TextArea
              rows={3}
              placeholder={td('switch.batch.form.descriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 链路聚合弹窗（仅 SSH 模式） */}
      {hasSsh && (
        <Modal
          title={td('switch.batch.modal.trunkTitle')}
          open={trunkModal.isOpen}
          onOk={handleTrunkOk}
          onCancel={() => {
            trunkModal.close();
            trunkForm.resetFields();
          }}
          destroyOnHidden
        >
          <Form form={trunkForm} layout="vertical">
            <Form.Item
              name="channel_id"
              label={td('switch.batch.form.trunkId')}
              rules={[{ required: true, message: td('switch.batch.form.trunkIdRequired') }]}
            >
              <InputNumber
                min={1}
                max={512}
                placeholder={td('switch.batch.form.trunkIdPlaceholder')}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Form>
        </Modal>
      )}

      {/* 客户分配弹窗 */}
      <Modal
        title={td('switch.batch.modal.customerTitle')}
        open={customerModal.isOpen}
        onOk={handleCustomerOk}
        onCancel={() => {
          customerModal.close();
          customerForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={customerForm} layout="vertical">
          <Form.Item name="customer_id" label={td('switch.batch.form.customer')}>
            <Select
              allowClear
              showSearch
              placeholder={td('switch.batch.form.customerPlaceholder')}
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
          title={td('switch.batch.modal.speedTitle')}
          open={speedModal.isOpen}
          onOk={handleSpeedOk}
          onCancel={() => {
            speedModal.close();
            speedForm.resetFields();
          }}
          destroyOnHidden
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={td('switch.batch.alert.speedPolicy')}
          />
          <Form form={speedForm} layout="vertical">
            <Form.Item
              name="inbound"
              label={td('switch.batch.form.inbound')}
              extra={td('switch.batch.form.inboundExtra')}
            >
              <InputNumber
                min={1}
                max={1000000}
                placeholder={td('switch.batch.form.inboundPlaceholder')}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item
              name="outbound"
              label={td('switch.batch.form.outbound')}
              extra={td('switch.batch.form.outboundExtra')}
            >
              <InputNumber
                min={1}
                max={1000000}
                placeholder={td('switch.batch.form.outboundPlaceholder')}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Form>
        </Modal>
      )}

      {/* 批量取消限速弹窗（仅 SSH 模式） */}
      {hasSsh && (
        <Modal
          title={td('switch.batch.modal.cancelSpeedTitle')}
          open={cancelSpeedModal.isOpen}
          onOk={handleCancelSpeedOk}
          onCancel={() => {
            cancelSpeedModal.close();
            cancelSpeedForm.resetFields();
          }}
          destroyOnHidden
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={td('switch.batch.alert.cancelSpeedTip')}
          />
          <Form
            form={cancelSpeedForm}
            layout="vertical"
            initialValues={{ cancel_inbound: true, cancel_outbound: true }}
          >
            <Form.Item name="cancel_inbound" valuePropName="checked">
              <Checkbox>{td('switch.batch.form.cancelInbound')}</Checkbox>
            </Form.Item>
            <Form.Item name="cancel_outbound" valuePropName="checked">
              <Checkbox>{td('switch.batch.form.cancelOutbound')}</Checkbox>
            </Form.Item>
          </Form>
        </Modal>
      )}
    </>
  );
}
