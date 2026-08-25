import { Tag } from 'antd';

interface StatusTagProps {
  status: string | number | null | undefined;
  statusMap: Record<string, { label: string; color: string }>;
}


export function StatusTag({ status, statusMap }: StatusTagProps) {
  const key = status == null ? '' : String(status);
  const cfg = statusMap[key];
  if (cfg) {
    return <Tag color={cfg.color}>{cfg.label}</Tag>;
  }
  return <Tag color="default">{status == null ? '-' : key}</Tag>;
}

export default StatusTag;
