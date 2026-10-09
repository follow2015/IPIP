import { Badge, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import type { SSEStatus } from '@/hooks/useSSEConnection';
import {
  SSE_BADGE_STATUS,
  SSE_STATUS_KEY,
  SSE_STATUS_SHORT_KEY,
  isSSEStatusVisible
} from './sseStatusMeta';

interface SSEStatusIndicatorProps {
  status: SSEStatus;
  compact?: boolean;
  'data-testid'?: string;
}

export default function SSEStatusIndicator({
  status,
  compact = false,
  'data-testid': testId = 'sse-status-indicator'
}: SSEStatusIndicatorProps) {
  const { t } = useTranslation();

  if (!isSSEStatusVisible(status)) return null;

  const description = status === 'degraded' ? `（${t('realtime.status.hint')}）` : '';
  const tooltip = `${t(SSE_STATUS_KEY[status])}${description}`;

  return (
    <Tooltip title={tooltip}>
      <Badge
        status={SSE_BADGE_STATUS[status]}
        text={compact ? undefined : t(SSE_STATUS_SHORT_KEY[status])}
        data-testid={testId}
        role="status"
        aria-label={tooltip}
      />
    </Tooltip>
  );
}
