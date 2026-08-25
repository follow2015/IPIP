/**
 * 网段详情页
 * - Card(基本信息+使用率+查看IP按钮) + Card(路由信息)
 * - 集成网段使用率统计（GET /api/network/usage）
 * - "查看网段IP"按钮跳转到IP管理页面并按网段搜索
 */
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Card, Button, Descriptions, Tag, Spin, Progress, Statistic, Row, Col } from 'antd';
import { ArrowLeftOutlined, SearchOutlined } from '@ant-design/icons';
import { useNetworkSuspenseDetail, useNetworkUsage } from '@/services/network';
import type { NetworkInfoListItem } from '@/types/models';
import { ROUTE_NOTES_MAP } from '@/types/enums';
import DataTable from '@/components/DataTable';


function NetworkDetail() {
  const { ipNetwork } = useParams<{ ipNetwork: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const roomId = searchParams.get('room_id') ? Number(searchParams.get('room_id')) : undefined;
  const switchId = searchParams.get('switch_id') ? Number(searchParams.get('switch_id')) : undefined;

  const networkName = decodeURIComponent(ipNetwork ?? '');

  const { data: detailData } = useNetworkSuspenseDetail(
    networkName,
    { page_size: 999, room_id: roomId, switch_id: switchId },
  );

  
  const { data: usageData } = useNetworkUsage(
    networkName,
  );

  
  const handleViewIPs = () => {
    const params = new URLSearchParams();
    params.set('search', networkName);
    navigate(`/ip?${params.toString()}`);
  };

  if (!detailData) {
    return <div>网段不存在</div>;
  }

  
  const routeColumns = [
    { title: '端口', dataIndex: 'port', key: 'port', render: (v: string | null) => v || '-' },
    { title: '下一跳', dataIndex: 'nexthop', key: 'nexthop', render: (v: string | null) => v || '-' },
    { title: '标志', dataIndex: 'flags', key: 'flags', render: (v: string | null) => v || '-' },
    { title: '类型', dataIndex: 'route_type', key: 'route_type', render: (v: number | string | null) => {
      if (v === null || v === undefined) return '-';
      const num = Number(v);
      const map = ROUTE_NOTES_MAP[num];
      return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
    }},
  ];

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/network')} style={{ marginBottom: 16 }}>
        返回列表
      </Button>

      {}
      <Card title={`网段详情 - ${networkName}`} extra={
        <Button type="primary" icon={<SearchOutlined />} onClick={handleViewIPs}>
          查看网段IP
        </Button>
      }>
        {detailData.network_info && (
          <Descriptions size="small" bordered column={3}>
            <Descriptions.Item label="网段">{detailData.network_info.network}</Descriptions.Item>
            <Descriptions.Item label="子网掩码">{detailData.network_info.subnet_mask ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="网关">{detailData.network_info.gateway ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="可用IP数">{detailData.network_info.usable_ips ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="IP范围">{detailData.network_info.start_ip} - {detailData.network_info.end_ip}</Descriptions.Item>
            <Descriptions.Item label="交换机">{detailData.network_info.switch_name ?? '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      {}
      {usageData && (
        <Card title="使用率" style={{ marginTop: 16 }}>
          <Row gutter={24} align="middle">
            <Col span={8}>
              <Progress
                type="circle"
                percent={Math.round(usageData.usage_rate * 100)}
                size={120}
                strokeColor={usageData.usage_rate > 0.8 ? '#ff4d4f' : usageData.usage_rate > 0.6 ? '#faad14' : '#52c41a'}
              />
            </Col>
            <Col span={16}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="总IP数" value={usageData.total_ips} />
                </Col>
                <Col span={8}>
                  <Statistic title="已使用" value={usageData.used_ips} styles={{ content: { color: '#1890ff' } }} />
                </Col>
                <Col span={8}>
                  <Statistic title="可用" value={usageData.available_ips} styles={{ content: { color: '#52c41a' } }} />
                </Col>
              </Row>
            </Col>
          </Row>
        </Card>
      )}

      {}
      {detailData.network_info_list && detailData.network_info_list.length > 0 && (
        <Card title="路由信息" style={{ marginTop: 16 }}>
          <DataTable
            columns={routeColumns}
            dataSource={detailData.network_info_list}
            rowKey={(r: NetworkInfoListItem) => `${r.switch_id}-${r.port}`}
            pagination={false}
            searchable={false}
            showCard={false}
          />
        </Card>
      )}
    </div>
  );
}

export default NetworkDetail;
