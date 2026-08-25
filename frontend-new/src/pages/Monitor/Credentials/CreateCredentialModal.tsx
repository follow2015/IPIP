/**
 * 新建共享凭据 Modal
 *
 * 从 Credentials/index.tsx 拆分（M26）：协议选择 + MonitorCredentialForm 复用。
 */
import { useState } from 'react';
import { Modal, Form, Select, Input, type FormInstance } from 'antd';
import { MONITOR_PROTOCOL_OPTIONS } from '@/types/enums';
import { useCreateAndLinkCredential } from '@/services/monitor';
import MonitorCredentialForm from '@/components/MonitorCredentialForm';
import { useMessage } from '@/hooks/useMessage';

interface CreateCredentialModalProps {
  open: boolean;
  form: FormInstance;
  onClose: () => void;
}

export default function CreateCredentialModal({ open, form, onClose }: CreateCredentialModalProps) {
  const [protocol, setProtocol] = useState<string>('snmp');
  const createLink = useCreateAndLinkCredential();
  const msg = useMessage();

  
  const handleSubmitForm = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    const p = values.protocol as string;
    const payload: Record<string, unknown> = {};

    if (p === 'snmp') {
      const ver = (values.snmp_version as string) || 'v2c';
      payload.version = ver;
      if (ver === 'v2c') {
        payload.community = values.community;
      } else {
        payload.username = values.username;
        payload.auth_key = values.auth_key;
        payload.priv_key = values.priv_key;
        payload.auth_protocol = values.auth_protocol || 'sha';
        payload.priv_protocol = values.priv_protocol || 'aes';
      }
    } else if (p === 'zabbix') {
      payload.api_url = values.api_url;
      payload.api_token = values.api_token;
      if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
      if (values.match_by) payload.match_by = values.match_by;
    } else {
      payload.username = values.username;
      payload.password = values.password;
      if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
    }

    try {
      await createLink.mutateAsync({
        protocol: p,
        payload,
        name: (values.name as string) || undefined,
        device_ids: []
      });
      msg.success('凭据已创建');
      onClose();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '创建失败');
    }
  };

  return (
    <Modal
      title="新建共享凭据"
      open={open}
      onCancel={onClose}
      onOk={handleSubmitForm}
      confirmLoading={createLink.isPending}
      width={520}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ protocol: 'snmp', snmp_version: 'v2c' }}>
        <Form.Item label="协议" name="protocol">
          <Select
            options={MONITOR_PROTOCOL_OPTIONS}
            onChange={(v) => {
              setProtocol(v);
              form.setFieldValue('snmp_version', 'v2c');
            }}
          />
        </Form.Item>

        <Form.Item
          label="凭据名称"
          name="name"
          rules={[{ required: true, message: '请输入凭据名称' }]}
        >
          <Input placeholder="如：机房A SNMP只读团体字" />
        </Form.Item>

        <MonitorCredentialForm protocol={protocol} mode="create" form={form} />
      </Form>
    </Modal>
  );
}
