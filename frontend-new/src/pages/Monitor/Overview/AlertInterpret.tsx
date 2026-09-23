import { useState } from 'react';
import { Button, Typography, Spin } from 'antd';
import { runSkill } from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

export interface AlertPayload {
  alert_type: string;
  device_name?: string;
  metric?: string;
  value?: number | string;
  unit?: string;
  severity?: string;
}

interface AlertInterpretProps {
  alert: AlertPayload;
}

export default function AlertInterpret({ alert }: AlertInterpretProps) {
  const { t } = useTranslation('monitor');
  const [text, setText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const message = useMessage();

  const run = async () => {
    setLoading(true);
    try {
      const result = await runSkill<string>('alert_interpret', { alert_payload: alert });
      setText(typeof result === 'string' ? result : JSON.stringify(result));
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('interpret.failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Button size="small" type="link" onClick={run} disabled={loading}>
        {t('interpret.run')}
      </Button>
      {loading && <Spin size="small" />}
      {text && <Typography.Paragraph style={{ marginTop: 8 }}>{text}</Typography.Paragraph>}
    </div>
  );
}
