import { useEffect } from 'react';
import { Modal, Form, Input, Select, Tag } from 'antd';
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
      title={`配置端口 IP — ${portName}`}
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
          <div style={{ marginBottom: 4, color: '#666' }}>当前已配置IP：</div>
          {currentIpList.map((ip, i) => (
            <Tag key={i} color={ip.is_primary ? 'blue' : 'default'} style={{ marginBottom: 2 }}>
              {ip.is_primary ? '主' : '从'} {ip.ip_address}
              {ip.prefix ? `/${ip.prefix}` : ip.subnet_mask ? `/${ip.subnet_mask}` : ''}
            </Tag>
          ))}
          <div style={{ marginTop: 6, color: '#faad14' }}>
            如需更换IP，请先在端口详情页IP地址栏删除原IP，再配置新IP。
          </div>
        </div>
      )}
      <Form form={form} layout="vertical">
        <Form.Item
          name="ip_address"
          label="IP 地址"
          rules={[
            { required: true, message: '请输入IP地址' },
            { pattern: /^(\d{1,3}\.){3}\d{1,3}$/, message: '请输入有效的IPv4地址' }
          ]}
        >
          <Input placeholder="192.168.1.1" />
        </Form.Item>
        <Form.Item
          name="subnet_mask"
          label="子网掩码"
          rules={[{ required: true, message: '请选择子网掩码' }]}
        >
          <Select options={SUBNET_MASK_OPTIONS} />
        </Form.Item>
        <Form.Item
          name="ip_type"
          label="IP 类型"
          help={hasPrimary ? '该端口已有主IP，默认添加为从IP' : '该端口暂无IP，将配置为主IP'}
        >
          <Select
            options={[
              { value: 'primary', label: '主 IP（ip address）' },
              { value: 'secondary', label: '从 IP（ip address sub/secondary）' }
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default IpConfigModal;
