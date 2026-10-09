import { Alert, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { getApiErrorMessage } from '@/utils/apiError';

export interface QueryErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  hasData?: boolean;
}

export default function QueryErrorState({ error, onRetry, hasData = false }: QueryErrorStateProps) {
  const { t } = useTranslation('common');
  const detail = getApiErrorMessage(error);

  const action = onRetry ? (
    <Button size="small" danger={!hasData} onClick={onRetry}>
      {t('action.retry')}
    </Button>
  ) : undefined;

  if (hasData) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t('message.requestFailed')}
        description={detail ?? undefined}
        action={action}
        style={{ marginBottom: 12 }}
      />
    );
  }

  return (
    <Alert
      type="error"
      showIcon
      message={t('message.requestFailed')}
      description={detail ?? undefined}
      action={action}
      style={{ marginBottom: 12 }}
    />
  );
}
