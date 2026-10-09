import { useMemo } from 'react';
import { Listy, Typography, Tag, theme } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface EvidenceListProps {
  evidence: string[];
}

export default function EvidenceList({ evidence }: EvidenceListProps) {
  const { t } = useTranslation('ai');
  const { token } = theme.useToken();

  const rows = useMemo(
    () => (evidence ?? []).map((text, i) => ({ key: `${i}-${text}`, text })),
    [evidence]
  );

  if (!evidence || evidence.length === 0) {
    return <Text type="secondary">{t('diagnosis.result.noEvidence')}</Text>;
  }

  return (
    <Listy
      items={rows}
      rowKey={(row) => row.key}
      itemRender={(row, index) => (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            width: '100%',
            minWidth: 0,
            padding: '4px 0'
          }}
        >
          <CheckCircleOutlined style={{ color: token.colorSuccess, marginTop: 4 }} />
          <Text style={{ flex: 1, minWidth: 0 }}>{row.text}</Text>
          <Tag color="blue">{t('diagnosis.result.evidenceTag', { index: index + 1 })}</Tag>
        </div>
      )}
    />
  );
}
