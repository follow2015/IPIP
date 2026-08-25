/**
 * IP 分配历史组件（嵌入 IP 详情页）
 * - 接收 ipAddress 和 roomId props
 * - 展示该 IP 的分配/释放/状态变更历史
 * - 使用 Table + Timeline 展示
 */
import { Table, Tag, Timeline } from 'antd';
import { useIPAllocationLogs } from '@/services/ip-allocation';
import type { IPAllocationLog } from '@/types/models';
import { IP_STATUS_MAP, IPStatusCode } from '@/types/enums';
import { formatDateTime } from '@/utils/format';


const ACTION_LABEL_MAP: Record<string, { label: string; color: string }> = {
  allocate: { label: '分配', color: 'green' },
  release: { label: '释放', color: 'orange' },
  change_status: { label: '状态变更', color: 'blue' },
};

interface AllocationHistoryProps {
  
  ipAddress: string;
  
  roomId?: number;
}


function renderStatusValue(v: number | null) {
  if (v === null) return '-';
  const info = IP_STATUS_MAP[v as IPStatusCode];
  return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{v}</Tag>;
}


function AllocationHistory({ ipAddress, roomId }: AllocationHistoryProps) {
  const { data, isLoading } = useIPAllocationLogs(ipAddress, roomId);
  const logs = data ?? [];

  
  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作类型',
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (v: string) => {
        const info = ACTION_LABEL_MAP[v];
        return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: '原状态',
      dataIndex: 'old_status',
      key: 'old_status',
      width: 80,
      render: renderStatusValue,
    },
    {
      title: '新状态',
      dataIndex: 'new_status',
      key: 'new_status',
      width: 80,
      render: renderStatusValue,
    },
    {
      title: '操作人',
      dataIndex: 'operator_id',
      key: 'operator_id',
      width: 100,
      render: (v: number) => `用户 #${v}`,
    },
  ];

  
  const timelineItems = logs.map((log) => {
    const actionInfo = ACTION_LABEL_MAP[log.action];
    return {
      key: log.id,
      color: actionInfo?.color ?? 'gray',
      children: (
        <div>
          <Tag color={actionInfo?.color}>{actionInfo?.label ?? log.action}</Tag>
          <span style={{ color: '#999', marginLeft: 8 }}>{formatDateTime(log.created_at)}</span>
          <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
            {renderStatusValue(log.old_status)} → {renderStatusValue(log.new_status)}
            <span style={{ marginLeft: 8 }}>操作人: 用户 #{log.operator_id}</span>
          </div>
        </div>
      ),
    };
  });

  return (
    <div>
      {}
      <Table<IPAllocationLog>
        columns={columns}
        dataSource={logs}
        loading={isLoading}
        rowKey="id"
        pagination={false}
        size="small"
      />

      {}
      {logs.length > 0 && logs.length <= 10 && (
        <div style={{ marginTop: 16 }}>
          <Timeline items={timelineItems} />
        </div>
      )}
    </div>
  );
}

export default AllocationHistory;
