/**
 * 新建共享凭据 Modal
 *
 * 从 Credentials/index.tsx 拆分（M26）：协议选择 + MonitorCredentialForm 复用。
 */
import { useState } from 'react';
import { Modal, Form, Select, Input, type FormInstance } from 'antd';
import { MONITOR_PROTOCOL_OPTIONS } from '@/types/enums';
import { useCreateSharedCredential } from '@/services/monitor';
import MonitorCredentialForm, { buildCredentialPayload } from '@/components/MonitorCredentialForm';
import { useMessage } from '@/hooks/useMessage';
import { useDirtyGuard } from '@/hooks/useDirtyGuard';
import { useTranslation } from 'react-i18next';

interface CreateCredentialModalProps {
  open: boolean;
  form: FormInstance;
  onClose: () => void;
}

export default function CreateCredentialModal({ open, form, onClose }: CreateCredentialModalProps) {
  const [protocol, setProtocol] = useState<string>('snmp');
  const createLink = useCreateSharedCredential();
  const msg = useMessage();
  const { t } = useTranslation('monitor');
  const { t: td } = useTranslation('device');

  const isPending = createLink.isPending;
  const guard = useDirtyGuard({ form, isPending });

  const handleSubmitForm = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    const p = values.protocol as string;
    const payload = buildCredentialPayload(p, values);

    try {
      await createLink.mutateAsync({
        protocol: p,
        payload,
        name: (values.name as string) || ''
      });
      msg.success(t('credential.message.created'));
      onClose();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : t('credential.message.createFailed'));
    }
  };

  return (
    <Modal
      title={t('credential.createTitle')}
      open={open}
      onCancel={() => guard.requestClose(onClose)}
      onOk={handleSubmitForm}
      confirmLoading={isPending}
      closable={!isPending}
      mask={{ closable: false }}
      width={520}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ protocol: 'snmp', snmp_version: 'v2c' }}>
        <Form.Item label={t('column.protocol')} name="protocol">
          <Select
            options={MONITOR_PROTOCOL_OPTIONS}
            onChange={(v) => {
              setProtocol(v);
              form.setFieldValue('snmp_version', 'v2c');
            }}
          />
        </Form.Item>

        <Form.Item
          label={td('credential.name')}
          name="name"
          rules={[{ required: true, message: td('credential.namePlaceholder') }]}
        >
          <Input placeholder={td('credential.nameHint')} />
        </Form.Item>

        <MonitorCredentialForm protocol={protocol} mode="create" />
      </Form>
    </Modal>
  );
}
