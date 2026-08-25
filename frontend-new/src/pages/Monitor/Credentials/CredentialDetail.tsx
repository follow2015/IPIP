/**
 * 凭据详情面板（右栏）
 *
 * 从 Credentials/index.tsx 拆分（M26）：选中凭据详情卡片 + 关联设备表。
 */
import { useState, useMemo } from 'react';
import { Card, Col, Row, Tag, Button, Space, Input, Empty, Typography, Tooltip } from 'antd';
import {
  LinkOutlined,
  DisconnectOutlined,
  SearchOutlined,
  LineChartOutlined
} from '@ant-design/icons';
import { MONITOR_PROTOCOL_COLOR_MAP } from '@/types/enums';
import { useNavigate } from 'react-router-dom';
import {
  useLinkedDevices,
  useUnlinkCredential,
  type MonitorCredentialListItem,
  type LinkedDevice
} from '@/services/monitor';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';

const { Text, Title } = Typography;

interface CredentialDetailProps {
  selectedCred: MonitorCredentialListItem | undefined;
  onOpenLink: () => void;
}

export default function CredentialDetail({ selectedCred, onOpenLink }: CredentialDetailProps) {
  const navigate = useNavigate();
  const msg = useMessage();
  const unlink = useUnlinkCredential();
  const linkedTable = useTable({ initialPerPage: 10 });

  const [deviceSearchKeyword, setDeviceSearchKeyword] = useState('');
  const { data: linkedDevices = [], isLoading: linkedLoading } = useLinkedDevices(
    selectedCred?.id ?? null
  );

  
  const filteredLinkedDevices = useMemo(() => {
    if (!deviceSearchKeyword) return linkedDevices;
    const kw = deviceSearchKeyword.toLowerCase();
    return linkedDevices.filter(
      (d) =>
        d.device_name.toLowerCase().includes(kw) ||
        (d.management_ip || '').toLowerCase().includes(kw)
    );
  }, [linkedDevices, deviceSearchKeyword]);

  
  const handleUnlink = async (deviceId: number) => {
    if (!selectedCred?.protocol) return;
    try {
      await unlink.mutateAsync({ deviceId, protocol: selectedCred.protocol });
      msg.success('已取消关联');
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  
  const linkedColumns = [
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: LinkedDevice) => (
        <a onClick={() => navigate(`/devices/${record.device_id}`)}>{name}</a>
      )
    },
    {
      title: '类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (t: string) => <Tag>{t}</Tag>
    },
    {
      title: '管理IP',
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      render: (ip: string | null) => ip || '—'
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: LinkedDevice) => (
        <Space size="small">
          <Tooltip title="查看历史趋势">
            <Button
              size="small"
              icon={<LineChartOutlined />}
              onClick={() => navigate(`/monitor/history?deviceId=${record.device_id}`)}
            />
          </Tooltip>
          <ConfirmButton
            size="small"
            icon={<DisconnectOutlined />}
            title="确认取消关联"
            content="确定要取消该设备与此凭据的关联吗？"
            okType="danger"
            onConfirm={() => handleUnlink(record.device_id)}
          >
            取消关联
          </ConfirmButton>
        </Space>
      )
    }
  ];

  if (!selectedCred) {
    return (
      <Card>
        <Empty description="请从左侧选择一个共享凭据查看详情" style={{ padding: '60px 0' }} />
      </Card>
    );
  }

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size={16}>
      {}
      <Card size="small">
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Title level={5} style={{ margin: 0 }}>
              {selectedCred.name || `${selectedCred.protocol} #${selectedCred.id}`}
            </Title>
          </Col>
          <Col>
            <Tag color={MONITOR_PROTOCOL_COLOR_MAP[selectedCred.protocol || ''] || 'default'}>
              {selectedCred.protocol?.toUpperCase()}
            </Tag>
          </Col>
        </Row>
        <Row gutter={24} style={{ marginTop: 12 }}>
          <Col span={8}>
            <Text type="secondary">状态</Text>
            <div>{selectedCred.enabled ? <Tag color="green">启用</Tag> : <Tag>已停用</Tag>}</div>
          </Col>
          <Col span={8}>
            <Text type="secondary">关联设备</Text>
            <div>
              <Text strong style={{ fontSize: 18 }}>
                {selectedCred.linked_count ?? 0}
              </Text>{' '}
              台
            </div>
          </Col>
          <Col span={8}>
            <Text type="secondary">凭据 ID</Text>
            <div>
              <Text code>{selectedCred.id}</Text>
            </div>
          </Col>
        </Row>
      </Card>

      {}
      <Card
        title="关联设备"
        extra={
          <Button type="primary" icon={<LinkOutlined />} onClick={onOpenLink}>
            关联设备
          </Button>
        }
      >
        <Input
          placeholder="搜索设备名称或 IP"
          prefix={<SearchOutlined />}
          allowClear
          value={deviceSearchKeyword}
          onChange={(e) => setDeviceSearchKeyword(e.target.value)}
          style={{ marginBottom: 12, maxWidth: 300 }}
        />
        <DataTable<LinkedDevice>
          columns={linkedColumns}
          dataSource={filteredLinkedDevices}
          loading={linkedLoading}
          rowKey={(r) => String(r.device_id)}
          total={filteredLinkedDevices.length}
          emptyText={deviceSearchKeyword ? '无匹配设备' : '暂无关联设备'}
          searchable={false}
          showCard={false}
          tableProps={linkedTable}
        />
      </Card>
    </Space>
  );
}
