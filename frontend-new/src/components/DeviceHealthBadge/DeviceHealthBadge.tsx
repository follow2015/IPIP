import { Tag, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDeviceMonitorStatus } from '@/services/monitor';
import { formatDateTime } from '@/utils/format';
import { WarningOutlined, EyeInvisibleOutlined } from '@ant-design/icons';

interface DeviceHealthBadgeProps {
  deviceId: number;
}

export function DeviceHealthBadge({ deviceId }: DeviceHealthBadgeProps) {
  const { data } = useDeviceMonitorStatus(deviceId);
  const { t } = useTranslation('device');

  if (!data || !data.monitored || !data.status) {
    return null;
  }

  const tags: React.ReactNode[] = [];

  if (data.monitor_interrupted) {
    tags.push(
      <Tag key="interrupted" color="orange" icon={<EyeInvisibleOutlined />}>
        {t('status.interrupted')}
      </Tag>
    );
  }

  if (data.status.reachable) {
    tags.push(
      <Tag key="reachable" color="green">
        {t('status.reachable')}
      </Tag>
    );
  } else {
    tags.push(
      <Tag key="unreachable" color="red">
        {t('health.unreachableSince', {
          time: formatDateTime(data.status.last_reachable_at)
        })}
      </Tag>
    );
  }

  const alertCount = data.active_metric_alerts ?? 0;
  if (alertCount > 0) {
    const sev = data.max_alert_severity ?? 0;
    const color = sev >= 3 ? 'magenta' : 'volcano';
    tags.push(
      <Tag key="metric-alert" color={color} icon={<WarningOutlined />}>
        {t('health.metricAlertCount', { count: alertCount })}
      </Tag>
    );
  }

  return <Space size={4}>{tags}</Space>;
}

export default DeviceHealthBadge;
