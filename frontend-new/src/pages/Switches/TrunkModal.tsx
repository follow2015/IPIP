import { useEffect } from 'react';
import { Modal, Form, InputNumber } from 'antd';
import { useTranslation } from 'react-i18next';

export interface TrunkValues {
  trunk_id: number;
}

interface TrunkModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  onSubmit: (values: TrunkValues) => void;
}

export function TrunkModal({ open, onClose, portName, onSubmit }: TrunkModalProps) {
  const { t } = useTranslation('device');
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({ trunk_id: Number(values.trunk_id) });
    } catch {
    }
  };

  return (
    <Modal
      title={t('switch.trunk.title', { name: portName })}
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
        <div>{t('switch.trunk.info1')}</div>
        <div>{t('switch.trunk.info2')}</div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item
          name="trunk_id"
          label={t('switch.batch.form.trunkId')}
          rules={[{ required: true, message: t('switch.trunk.trunkIdRequired') }]}
        >
          <InputNumber
            min={0}
            placeholder={t('switch.trunk.trunkIdPlaceholder')}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default TrunkModal;
