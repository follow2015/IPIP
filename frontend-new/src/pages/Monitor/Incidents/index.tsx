import { useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Select,
  Button,
  Drawer,
  Descriptions,
  Typography,
  Tooltip
} from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  useIncidents,
  useIncidentDetail,
  type IncidentItem,
  type IncidentListParams
} from '@/services/monitor';
import { formatDateTime } from '@/utils/format';

const { Text } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  info: 'blue'
};

const REASON_LABEL: Record<string, string> = {
  L1_rule: '规则聚合',
  L2_topology: '拓扑聚合',
  L2_manual_rule: '手动规则聚合',
  L3_change: '变更关联'
};

const STATUS_COLOR: Record<string, string> = {
  active: 'processing',
  acknowledged: 'warning',
  closed: 'default'
};

export default function MonitorIncidents() {
  const [params, setParams] = useState<IncidentListParams>({
    page: 1,
    per_page: 20
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, isLoading, refetch, isFetching } = useIncidents(params);
  const { data: detail, isLoading: detailLoading } = useIncidentDetail(selectedId);

  const items = (data?.items ?? []) as IncidentItem[];
  const total = data?.total ?? 0;

  const columns: ColumnsType<IncidentItem> = [
    {
      title: '事件标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, row) => (
        <Tooltip title={title}>
          <a onClick={() => setSelectedId(row.id)}>{title}</a>
        </Tooltip>
      )
    },
    {
      title: '严重级别',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (s: string) => <Tag color={SEVERITY_COLOR[s] ?? 'default'}>{s}</Tag>
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] ?? 'default'}>{s}</Tag>
    },
    {
      title: '告警数',
      dataIndex: 'alert_count',
      key: 'alert_count',
      width: 80,
      align: 'right'
    },
    {
      title: '影响设备数',
      dataIndex: 'device_count',
      key: 'device_count',
      width: 100,
      align: 'right',
      render: (n: number) => (
        <Text strong style={{ color: n > 1 ? '#cf1322' : undefined }}>
          {n}
        </Text>
      )
    },
    {
      title: '归并原因',
      dataIndex: 'reason_code',
      key: 'reason_code',
      width: 120,
      render: (r: string | null) => (r ? (REASON_LABEL[r] ?? r) : '-')
    },
    {
      title: '首告时间',
      dataIndex: 'first_alert_at',
      key: 'first_alert_at',
      width: 160,
      render: (t: string | null) => (t ? formatDateTime(t) : '-')
    },
    {
      title: '末告时间',
      dataIndex: 'last_alert_at',
      key: 'last_alert_at',
      width: 160,
      render: (t: string | null) => (t ? formatDateTime(t) : '-')
    }
  ];

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined />
          <span>事件中心</span>
        </Space>
      }
      extra={
        <Space>
          <Select
            allowClear
            placeholder="状态过滤"
            style={{ width: 140 }}
            value={params.status}
            onChange={(v) => setParams((p) => ({ ...p, status: v || undefined, page: 1 }))}
            options={[
              { value: 'active', label: '活跃' },
              { value: 'acknowledged', label: '已确认' },
              { value: 'closed', label: '已关闭' }
            ]}
          />
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
            刷新
          </Button>
        </Space>
      }
    >
      <Table<IncidentItem>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={isLoading}
        pagination={{
          current: params.page,
          pageSize: params.per_page,
          total: total,
          showSizeChanger: true,
          onChange: (page, per_page) => setParams((p) => ({ ...p, page, per_page }))
        }}
        onRow={(row) => ({ onClick: () => setSelectedId(row.id) })}
      />

      <Drawer
        title="事件详情"
        open={selectedId != null}
        onClose={() => setSelectedId(null)}
        width={680}
        loading={detailLoading}
      >
        {detail && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="事件标题" span={2}>
                {detail.title}
              </Descriptions.Item>
              <Descriptions.Item label="严重级别">
                <Tag color={SEVERITY_COLOR[detail.severity] ?? 'default'}>{detail.severity}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[detail.status] ?? 'default'}>{detail.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="告警数">{detail.alert_count}</Descriptions.Item>
              <Descriptions.Item label="影响设备数">
                <Text strong style={{ color: detail.device_count > 1 ? '#cf1322' : undefined }}>
                  {detail.device_count}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="归并原因">
                {detail.reason_code
                  ? (REASON_LABEL[detail.reason_code] ?? detail.reason_code)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="根因设备">{detail.root_device_id ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="首告时间">
                {detail.first_alert_at ? formatDateTime(detail.first_alert_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="末告时间">
                {detail.last_alert_at ? formatDateTime(detail.last_alert_at) : '-'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title={`关联告警（${detail.related_alerts.length}）`}>
              <Table
                rowKey="id"
                size="small"
                pagination={{ pageSize: 5 }}
                dataSource={detail.related_alerts}
                columns={[
                  { title: 'ID', dataIndex: 'id', width: 70 },
                  { title: '类型', dataIndex: 'alert_type', width: 140 },
                  { title: '严重级别', dataIndex: 'severity', width: 90 },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    render: (t: string | null) => (t ? formatDateTime(t) : '-')
                  }
                ]}
              />
            </Card>

            <Card size="small" title={`被抑制的下游设备（${detail.suppressed_logs.length}）`}>
              <Table
                rowKey={(r) => `${r.device_id}-${r.created_at}`}
                size="small"
                pagination={{ pageSize: 5 }}
                dataSource={detail.suppressed_logs}
                columns={[
                  { title: '设备 ID', dataIndex: 'device_id', width: 90 },
                  { title: '告警类型', dataIndex: 'alert_type', width: 140 },
                  { title: '严重级别', dataIndex: 'severity', width: 90 },
                  { title: '上游设备', dataIndex: 'upstream_device_id', width: 100 },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    render: (t: string | null) => (t ? formatDateTime(t) : '-')
                  }
                ]}
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </Card>
  );
}
