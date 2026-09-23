import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';

import type { StatusLabelKey } from '@/types/statusMeta';

interface StatusTagProps {
  status: string | number | null | undefined;
  statusMap: Record<string, { labelKey: StatusLabelKey; color: string }>;
}

export function StatusTag({ status, statusMap }: StatusTagProps) {
  const { t } = useTranslation('device');
  const key = status == null ? '' : String(status);
  const cfg = statusMap[key];
  if (cfg) {
    return <Tag color={cfg.color}>{(t as (k: string) => string)(cfg.labelKey)}</Tag>;
  }
  return <Tag color="default">{status == null ? '-' : key}</Tag>;
}

export default StatusTag;
