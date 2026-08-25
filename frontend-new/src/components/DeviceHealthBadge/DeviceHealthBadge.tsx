import { Tag, Space } from 'antd';
import { useDeviceMonitorStatus } from '@/services/monitor';
import { formatDateTime } from '@/utils/format';
import { WarningOutlined, EyeInvisibleOutlined } from '@ant-design/icons';

interface DeviceHealthBadgeProps {
  deviceId: number;
}


export function DeviceHealthBadge({ deviceId }: DeviceHealthBadgeProps) {
  const { data } = useDeviceMonitorStatus(deviceId);

  if (!data || !data.monitored || !data.status) {
    return null;
  }

  const tags: React.ReactNode[] = [];

  
  if (data.monitor_interrupted) {
    tags.push(
      <Tag key="interrupted" color="orange" icon={<EyeInvisibleOutlined />}>
        中断
      </Tag>
    );
  }

  
  if (data.status.reachable) {
    tags.push(
      <Tag key="reachable" color="green">
        可达
      </Tag>
    );
  } else {
    tags.push(
      <Tag key="unreachable" color="red">
        不可达（上次可达：{formatDateTime(data.status.last_reachable_at)}）
      </Tag>
    );
  }

  
  const alertCount = data.active_metric_alerts ?? 0;
  if (alertCount > 0) {
    const sev = data.max_alert_severity ?? 0;
    const color = sev >= 3 ? 'magenta' : 'volcano';
    tags.push(
      <Tag key="metric-alert" color={color} icon={<WarningOutlined />}>
        指标告警 {alertCount}
      </Tag>
    );
  }

  return <Space size={4}>{tags}</Space>;
}

export default DeviceHealthBadge;
