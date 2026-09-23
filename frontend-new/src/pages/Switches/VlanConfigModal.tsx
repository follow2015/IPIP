import { useEffect } from 'react';
import { Modal, Form, InputNumber, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';

export interface VlanConfigValues {
  vlan_id: number;
  mode: 'access' | 'trunk';
  allowed_vlans?: string;
}

interface VlanConfigModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  portType: string;
  initialVlanId?: number;
  onSubmit: (values: VlanConfigValues) => void;
}

export function VlanConfigModal({
  open,
  onClose,
  portName,
  portType,
  initialVlanId,
  onSubmit
}: VlanConfigModalProps) {
  const { t } = useTranslation('device');
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ vlan_id: initialVlanId ?? undefined, mode: 'access' });
    }
  }, [open, initialVlanId, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({
        vlan_id: Number(values.vlan_id),
        mode: values.mode as 'access' | 'trunk',
        allowed_vlans: values.allowed_vlans as string | undefined
      });
    } catch {
    }
  };

  return (
    <Modal
      title={t('switch.vlanConfig.title', { name: portName })}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnHidden
    >
      <div
        style={{
          marginBottom: 12,
          padding: 8,
          background: '#fff2f0',
          borderRadius: 4,
          fontSize: 12,
          color: '#cf1322',
          lineHeight: 1.8,
          border: '1px solid #ffccc7'
        }}
      >
        <div>{t('switch.portConfigWarning')}</div>
      </div>
      <div
        style={{
          marginBottom: 12,
          padding: 8,
          background: '#f6f8fa',
          borderRadius: 4,
          fontSize: 12,
          color: '#666',
          lineHeight: 1.8
        }}
      >
        <div>{t('switch.vlanConfig.info1')}</div>
        <div>{t('switch.vlanConfig.info2')}</div>
        <div>{t('switch.vlanConfig.info3')}</div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.mode !== cur.mode}>
          {({ getFieldValue }) => (
            <Form.Item
              name="vlan_id"
              label={
                getFieldValue('mode') === 'trunk'
                  ? t('switch.vlanConfig.pvidLabel')
                  : t('switch.vlanConfig.vlanIdLabel')
              }
              rules={[{ required: true, message: t('switch.vlanConfig.vlanIdRequired') }]}
            >
              <InputNumber
                min={1}
                max={4094}
                style={{ width: '100%' }}
                disabled={portType === 'vlan'}
                placeholder={
                  getFieldValue('mode') === 'trunk'
                    ? t('switch.vlanConfig.pvidPlaceholder')
                    : t('switch.vlanConfig.vlanIdPlaceholder')
                }
              />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item name="mode" label={t('switch.vlanConfig.portMode')} rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'access', label: t('switch.vlanConfig.modeAccess') },
              { value: 'trunk', label: t('switch.vlanConfig.modeTrunk') }
            ]}
          />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.mode !== cur.mode}>
          {({ getFieldValue }) =>
            getFieldValue('mode') === 'trunk' ? (
              <Form.Item
                name="allowed_vlans"
                label={t('switch.vlanConfig.allowedVlans')}
                rules={[{ required: true, message: t('switch.vlanConfig.allowedVlansRequired') }]}
                help={t('switch.vlanConfig.allowedVlansHelp')}
              >
                <Input placeholder="1-10,20,30-40" />
              </Form.Item>
            ) : null
          }
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default VlanConfigModal;
