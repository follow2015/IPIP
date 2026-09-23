import { useEffect } from 'react';
import { Modal, Form, Input, Select, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import type { SwitchPortIP } from '@/types/models';

export interface IpConfigValues {
  ip_address: string;
  subnet_mask: string;
  ip_type: 'primary' | 'secondary';
}

const SUBNET_MASK_OPTIONS = [
  { value: '255.255.255.252', label: '255.255.255.252 (/30)' },
  { value: '255.255.255.248', label: '255.255.255.248 (/29)' },
  { value: '255.255.255.240', label: '255.255.255.240 (/28)' },
  { value: '255.255.255.224', label: '255.255.255.224 (/27)' },
  { value: '255.255.255.192', label: '255.255.255.192 (/26)' },
  { value: '255.255.255.128', label: '255.255.255.128 (/25)' },
  { value: '255.255.255.0', label: '255.255.255.0 (/24)' },
  { value: '255.255.254.0', label: '255.255.254.0 (/23)' },
  { value: '255.255.252.0', label: '255.255.252.0 (/22)' },
  { value: '255.255.0.0', label: '255.255.0.0 (/16)' },
  { value: '255.0.0.0', label: '255.0.0.0 (/8)' }
];

interface IpConfigModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  currentIpList?: SwitchPortIP[];
  hasPrimary: boolean;
  onSubmit: (values: IpConfigValues) => void;
}

export function IpConfigModal({
  open,
  onClose,
  portName,
  currentIpList,
  hasPrimary,
  onSubmit
}: IpConfigModalProps) {
  const { t } = useTranslation('device');
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({
        ip_address: '',
        subnet_mask: '255.255.255.0',
        ip_type: hasPrimary ? 'secondary' : 'primary'
      });
    }
  }, [open, hasPrimary, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({
        ip_address: String(values.ip_address),
        subnet_mask: String(values.subnet_mask),
        ip_type: values.ip_type as 'primary' | 'secondary'
      });
    } catch {
    }
  };

  return (
    <Modal
      title={t('switch.ipConfig.title', { name: portName })}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnHidden
    >
      {currentIpList && currentIpList.length > 0 && (
        <div
          style={{
            marginBottom: 12,
            padding: 8,
            background: '#f8f9fa',
            borderRadius: 4,
            fontSize: 12
          }}
        >
          <div style={{ marginBottom: 4, color: '#666' }}>{t('switch.ipConfig.currentLabel')}</div>
          {currentIpList.map((ip, i) => (
            <Tag key={i} color={ip.is_primary ? 'blue' : 'default'} style={{ marginBottom: 2 }}>
              {ip.is_primary ? t('port.ipRole.primary') : t('port.ipRole.secondary')}{' '}
              {ip.ip_address}
              {ip.prefix ? `/${ip.prefix}` : ip.subnet_mask ? `/${ip.subnet_mask}` : ''}
            </Tag>
          ))}
          <div style={{ marginTop: 6, color: '#faad14' }}>{t('switch.ipConfig.replaceHint')}</div>
        </div>
      )}
      <Form form={form} layout="vertical">
        <Form.Item
          name="ip_address"
          label={t('port.column.ipAddress')}
          rules={[
            { required: true, message: t('switch.ipConfig.addressRequired') },
            { pattern: /^(\d{1,3}\.){3}\d{1,3}$/, message: t('switch.ipConfig.addressInvalid') }
          ]}
        >
          <Input placeholder="192.168.1.1" />
        </Form.Item>
        <Form.Item
          name="subnet_mask"
          label={t('switch.ipConfig.subnetMask')}
          rules={[{ required: true, message: t('switch.ipConfig.subnetMaskRequired') }]}
        >
          <Select options={SUBNET_MASK_OPTIONS} />
        </Form.Item>
        <Form.Item
          name="ip_type"
          label={t('switch.ipConfig.ipType')}
          help={
            hasPrimary ? t('switch.ipConfig.helpHasPrimary') : t('switch.ipConfig.helpNoPrimary')
          }
        >
          <Select
            options={[
              { value: 'primary', label: t('switch.ipConfig.typePrimary') },
              { value: 'secondary', label: t('switch.ipConfig.typeSecondary') }
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default IpConfigModal;
