/**
 * IP 分配历史组件（嵌入 IP 详情页）
 * - 接收 ipAddress 和 roomId props
 * - 展示该 IP 的分配/释放/状态变更历史
 * - 使用 Table + Timeline 展示
 */
import { Table, Tag, Timeline } from 'antd';
import { useIPAllocationLogs } from '@/services/ip-allocation';
import type { IPAllocationLog } from '@/types/models';
import { getIPStatusMeta, type DeviceT } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';

type AllocationActionKey =
  | 'allocation.action.allocate'
  | 'allocation.action.release'
  | 'allocation.action.changeStatus';

const ACTION_LABEL_MAP: Record<string, { labelKey: AllocationActionKey; color: string }> = {
  allocate: { labelKey: 'allocation.action.allocate', color: 'green' },
  release: { labelKey: 'allocation.action.release', color: 'orange' },
  change_status: { labelKey: 'allocation.action.changeStatus', color: 'blue' },
};

interface AllocationHistoryProps {
  ipAddress: string;
  roomId?: number;
}

function renderStatusValue(v: number | null, t: DeviceT) {
  if (v === null) return '-';
  const info = getIPStatusMeta(v, t);
  return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{v}</Tag>;
}

function AllocationHistory({ ipAddress, roomId }: AllocationHistoryProps) {
  const { t: td } = useTranslation('device');
  const { t } = useTranslation('network');
  const { data, isLoading } = useIPAllocationLogs(ipAddress, roomId);
  const logs = data ?? [];

  const columns = [
    {
      title: t('allocation.field.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('allocation.field.actionType'),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (v: string) => {
        const info = ACTION_LABEL_MAP[v];
        return info ? <Tag color={info.color}>{t(info.labelKey)}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: t('allocation.field.oldStatus'),
      dataIndex: 'old_status',
      key: 'old_status',
      width: 80,
      render: (v: number | null) => renderStatusValue(v, td),
    },
    {
      title: t('allocation.field.newStatus'),
      dataIndex: 'new_status',
      key: 'new_status',
      width: 80,
      render: (v: number | null) => renderStatusValue(v, td),
    },
    {
      title: t('allocation.field.operator'),
      dataIndex: 'operator_id',
      key: 'operator_id',
      width: 100,
      render: (v: number) => t('allocation.userFallback', { id: v }),
    },
  ];

  const timelineItems = logs.map((log) => {
    const actionInfo = ACTION_LABEL_MAP[log.action];
    return {
      key: log.id,
      color: actionInfo?.color ?? 'gray',
      children: (
        <div>
          <Tag color={actionInfo?.color}>
            {actionInfo ? t(actionInfo.labelKey) : log.action}
          </Tag>
          <span style={{ color: '#999', marginLeft: 8 }}>{formatDateTime(log.created_at)}</span>
          <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
            {renderStatusValue(log.old_status, td)} → {renderStatusValue(log.new_status, td)}
            <span style={{ marginLeft: 8 }}>
              {t('allocation.operator', { id: log.operator_id })}
            </span>
          </div>
        </div>
      ),
    };
  });

  return (
    <div>
      {/* 表格视图 */}
      <Table<IPAllocationLog>
        columns={columns}
        dataSource={logs}
        loading={isLoading}
        rowKey="id"
        pagination={false}
        size="small"
      />

      {/* Timeline 视图（可选，数据量少时更直观） */}
      {logs.length > 0 && logs.length <= 10 && (
        <div style={{ marginTop: 16 }}>
          <Timeline items={timelineItems} />
        </div>
      )}
    </div>
  );
}

export default AllocationHistory;
