import { useMemo } from 'react';
import { Divider, Listy, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

const { Paragraph } = Typography;

export interface RagReferenceItem {
  doc_id?: string | null;
  text?: string;
}

interface RagReferencesProps {
  references: RagReferenceItem[];
}

export default function RagReferences({ references }: RagReferencesProps) {
  const { t } = useTranslation('ai');

  const rows = useMemo(
    () =>
      (references ?? []).map((ref, i) => ({
        key: `${i}-${ref.doc_id ?? ''}-${(ref.text ?? '').slice(0, 24)}`,
        ref,
        index: i
      })),
    [references]
  );

  if (!references || references.length === 0) return null;

  return (
    <>
      <Divider />
      <Paragraph type="secondary">
        {t('rag.answer.hitFragments', { count: references.length })}
      </Paragraph>
      <Listy
        items={rows}
        rowKey={(row) => row.key}
        itemRender={(row) => (
          <div style={{ minWidth: 0 }}>
            <div style={{ marginBottom: 4 }}>
              [{row.index + 1}] {row.ref.doc_id || '-'}
            </div>
            <Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
              {row.ref.text}
            </Paragraph>
          </div>
        )}
      />
    </>
  );
}
