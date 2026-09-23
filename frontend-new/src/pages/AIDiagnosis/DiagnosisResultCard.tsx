import { Card, Typography, Progress, Tag, Alert } from 'antd';
import { type DiagnosisResult } from '@/services/diagnosis';
import { useTranslation } from 'react-i18next';
import EvidenceList from './EvidenceList';

const { Paragraph, Text } = Typography;

interface DiagnosisResultCardProps {
  result: DiagnosisResult;
}

export default function DiagnosisResultCard({ result }: DiagnosisResultCardProps) {
  const { t } = useTranslation('ai');
  const confidencePct = Math.round((result.confidence || 0) * 100);
  const confidenceColor =
    confidencePct >= 70 ? '#52c41a' : confidencePct >= 40 ? '#faad14' : '#ff4d4f';

  return (
    <Card
      title={
        <span>
          {t('diagnosis.result.title')}
          {result.incomplete && (
            <Tag color="orange" style={{ marginLeft: 8 }}>
              {t('diagnosis.result.incomplete')}
            </Tag>
          )}
        </span>
      }
      size="small"
    >
      {result.incomplete && (
        <Alert
          type="warning"
          message={t('diagnosis.result.incompleteTitle')}
          description={t('diagnosis.result.incompleteDesc')}
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      <Paragraph>
        <Text strong>{t('diagnosis.result.rootCause')}</Text>
        <br />
        <Text>{result.diagnosis}</Text>
      </Paragraph>

      <div style={{ marginBottom: 12 }}>
        <Text strong>{t('diagnosis.result.confidence')}</Text>
        <Progress
          percent={confidencePct}
          strokeColor={confidenceColor}
          size="small"
          style={{ display: 'inline-block', width: 200, marginLeft: 8 }}
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <Text strong>{t('diagnosis.result.evidence')}</Text>
        <EvidenceList evidence={result.evidence || []} />
      </div>
    </Card>
  );
}
