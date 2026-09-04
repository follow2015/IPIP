import { useEffect, useRef, useState } from 'react';
import { Card, Input, Button, Typography, Space } from 'antd';
import { SendOutlined, RobotOutlined } from '@ant-design/icons';
import { ask } from '@/services/ai';
import { useMessage } from '@/hooks/useMessage';

const { Paragraph, Text } = Typography;

export default function NLQuery() {
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
      message.warning('请输入问题');
      return;
    }
    if (question.length > 2000) {
      message.warning('问题过长，请控制在 2000 字以内');
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
      message.error(err instanceof Error ? err.message : '查询失败');
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
          <span>AI 智能查询</span>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Paragraph type="secondary">
          用自然语言查询运维数据，例如：「哪台设备 CPU 最高」「各机房有多少设备」「巡检异常设备」
        </Paragraph>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="输入你的问题..."
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
            查询
          </Button>
        </Space.Compact>
        {answer && (
          <Card type="inner" title="查询结果">
            <Text style={{ whiteSpace: 'pre-wrap' }}>{answer}</Text>
          </Card>
        )}
      </Space>
    </Card>
  );
}
