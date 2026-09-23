import { List, Typography, Tag } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface EvidenceListProps {
  evidence: string[];
}

export default function EvidenceList({ evidence }: EvidenceListProps) {
  const { t } = useTranslation('ai');
  if (!evidence || evidence.length === 0) {
    return <Text type="secondary">{t('diagnosis.result.noEvidence')}</Text>;
  }
  return (
    <List
      size="small"
      dataSource={evidence}
      renderItem={(item, idx) => (
        <List.Item>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, width: '100%' }}>
            <CheckCircleOutlined style={{ color: '#52c41a', marginTop: 4 }} />
            <Text style={{ flex: 1 }}>{item}</Text>
            <Tag color="blue">{t('diagnosis.result.evidenceTag', { index: idx + 1 })}</Tag>
          </div>
        </List.Item>
      )}
    />
  );
}
