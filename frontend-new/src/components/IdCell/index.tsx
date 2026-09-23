import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';

interface IdCellProps {
  value: number | string | null | undefined;
}

export default function IdCell({ value }: IdCellProps) {
  const message = useMessage();
  const { t } = useTranslation();

  if (value === null || value === undefined || value === '') {
    return <span>-</span>;
  }

  const handleCopy = () => {
    const text = String(value);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => message.success(t('message.idCopied')))
        .catch(() => message.error(t('message.copyFailedManual')));
    } else {
      message.error(t('message.copyUnsupported'));
    }
  };

  return (
    <span
      onClick={handleCopy}
      title={t('action.copyId')}
      style={{
        cursor: 'pointer',
        fontFamily: 'monospace',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4
      }}
    >
      {value}
      <CopyOutlined style={{ fontSize: 12, opacity: 0.45 }} />
    </span>
  );
}
