import { useEffect, useRef, useState } from 'react';
import { Card, Input, Button, Typography, Space } from 'antd';
import { SendOutlined, RobotOutlined } from '@ant-design/icons';
import { ask } from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

const { Paragraph, Text } = Typography;

export default function NLQuery() {
  const { t } = useTranslation('ai');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const message = useMessage();

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const handleAsk = async () => {
    if (!question.trim()) {
      message.warning(t('validation.enterQuestion'));
      return;
    }
    if (question.length > 2000) {
      message.warning(t('nlq.validation.questionTooLong'));
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setAnswer('');
    try {
      const result = await ask(question, controller.signal);
      if (!mountedRef.current) return;
      setAnswer(result);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : t('nlq.message.queryFailed'));
    } finally {
      if (mountedRef.current && !controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  return (
    <Card
      title={
        <Space>
          <RobotOutlined />
          <span>{t('nlq.title')}</span>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Paragraph type="secondary">{t('nlq.description')}</Paragraph>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('nlq.placeholder')}
            onPressEnter={handleAsk}
            disabled={loading}
            size="large"
            maxLength={2000}
            showCount
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleAsk}
            loading={loading}
            size="large"
          >
            {t('nlq.action')}
          </Button>
        </Space.Compact>
        {answer && (
          <Card type="inner" title={t('nlq.result')}>
            <Text style={{ whiteSpace: 'pre-wrap' }}>{answer}</Text>
          </Card>
        )}
      </Space>
    </Card>
  );
}
