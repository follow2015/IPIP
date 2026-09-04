import { Card, Typography, Progress, Tag, Alert } from 'antd';
import { type DiagnosisResult } from '@/services/diagnosis';
import EvidenceList from './EvidenceList';

const { Paragraph, Text } = Typography;

interface DiagnosisResultCardProps {
  result: DiagnosisResult;
}

export default function DiagnosisResultCard({ result }: DiagnosisResultCardProps) {
  const confidencePct = Math.round((result.confidence || 0) * 100);
  const confidenceColor =
    confidencePct >= 70 ? '#52c41a' : confidencePct >= 40 ? '#faad14' : '#ff4d4f';

  return (
    <Card
      title={
        <span>
          诊断结论
          {result.incomplete && (
            <Tag color="orange" style={{ marginLeft: 8 }}>
              未完成
            </Tag>
          )}
        </span>
      }
      size="small"
    >
      {result.incomplete && (
        <Alert
          type="warning"
          message="诊断未完成"
          description="已采集多轮数据但未能定位根因，建议人工介入。"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      <Paragraph>
        <Text strong>根因：</Text>
        <br />
        <Text>{result.diagnosis}</Text>
      </Paragraph>

      <div style={{ marginBottom: 12 }}>
        <Text strong>置信度：</Text>
        <Progress
          percent={confidencePct}
          strokeColor={confidenceColor}
          size="small"
          style={{ display: 'inline-block', width: 200, marginLeft: 8 }}
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <Text strong>证据：</Text>
        <EvidenceList evidence={result.evidence || []} />
      </div>
    </Card>
  );
}
