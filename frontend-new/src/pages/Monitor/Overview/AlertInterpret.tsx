import { useState } from 'react';
import { Button, Typography, Spin, App } from 'antd';
import { runSkill } from '@/services/ai';

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
  const [text, setText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const { message } = App.useApp();

  const run = async () => {
    setLoading(true);
    try {
      const result = await runSkill<string>('alert_interpret', { alert_payload: alert });
      setText(typeof result === 'string' ? result : JSON.stringify(result));
    } catch (err) {
      message.error(err instanceof Error ? err.message : 'AI 解读失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Button size="small" type="link" onClick={run} disabled={loading}>
        AI 解读
      </Button>
      {loading && <Spin size="small" />}
      {text && <Typography.Paragraph style={{ marginTop: 8 }}>{text}</Typography.Paragraph>}
    </div>
  );
}
