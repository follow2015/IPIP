import { useEffect } from 'react';
import { Modal, Form, InputNumber } from 'antd';
import { useTranslation } from 'react-i18next';

export interface SpeedLimitValues {
  inbound: number;
  outbound: number;
}

interface SpeedLimitModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  maxSpeed: number;
  onSubmit: (values: SpeedLimitValues) => void;
}

export function SpeedLimitModal({
  open,
  onClose,
  portName,
  maxSpeed,
  onSubmit
}: SpeedLimitModalProps) {
  const { t } = useTranslation('device');
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({ inbound: Number(values.inbound), outbound: Number(values.outbound) });
    } catch {
    }
  };

  return (
    <Modal
      title={t('switch.speed.title', { name: portName })}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnHidden
      width={480}
    >
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
        <div>{t('switch.speed.infoPolicy')}</div>
        <div>
          <b>{t('switch.speed.inboundLabel')}</b>
          {t('switch.speed.inboundDesc')}
        </div>
        <div>
          <b>{t('switch.speed.outboundLabel')}</b>
          {t('switch.speed.outboundDesc')}
        </div>
        <div>
          {t('switch.speed.zeroPrefix')}
          <b>0</b>
          {t('switch.speed.zeroSuffix', { max: maxSpeed })}
        </div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item
          name="inbound"
          label={t('switch.speed.inbound')}
          rules={[{ required: true, message: t('switch.speed.inboundRequired') }]}
        >
          <InputNumber
            min={0}
            max={maxSpeed}
            placeholder={t('switch.speed.rangePlaceholder', { max: maxSpeed })}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item
          name="outbound"
          label={t('switch.speed.outbound')}
          rules={[{ required: true, message: t('switch.speed.outboundRequired') }]}
        >
          <InputNumber
            min={0}
            max={maxSpeed}
            placeholder={t('switch.speed.rangePlaceholder', { max: maxSpeed })}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default SpeedLimitModal;
