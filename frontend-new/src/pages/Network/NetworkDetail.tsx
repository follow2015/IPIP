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
import { getRouteNoteMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import DataTable from '@/components/DataTable';

function NetworkDetail() {
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const { ipNetwork } = useParams<{ ipNetwork: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const roomId = searchParams.get('room_id') ? Number(searchParams.get('room_id')) : undefined;
  const switchId = searchParams.get('switch_id')
    ? Number(searchParams.get('switch_id'))
    : undefined;

  const networkName = decodeURIComponent(ipNetwork ?? '');

  const { data: detailData } = useNetworkSuspenseDetail(networkName, {
    page_size: 999,
    room_id: roomId,
    switch_id: switchId
  });

  const { data: usageData } = useNetworkUsage(networkName);

  const handleViewIPs = () => {
    const params = new URLSearchParams();
    params.set('search', networkName);
    navigate(`/ip?${params.toString()}`);
  };

  if (!detailData) {
    return <div>{t('networkDetail.notFound')}</div>;
  }

  const routeColumns = [
    {
      title: t('networkList.field.port'),
      dataIndex: 'port',
      key: 'port',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.nexthop'),
      dataIndex: 'nexthop',
      key: 'nexthop',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkDetail.field.flags'),
      dataIndex: 'flags',
      key: 'flags',
      render: (v: string | null) => v || '-'
    },
    {
      title: tc('field.type'),
      dataIndex: 'route_type',
      key: 'route_type',
      render: (v: number | string | null) => {
        if (v === null || v === undefined) return '-';
        const num = Number(v);
        const map = getRouteNoteMeta(num, td);
        return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
      }
    }
  ];

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/network')}
        style={{ marginBottom: 16 }}
      >
        {td('detail.backToList')}
      </Button>

      {/* 基本信息 Card */}
      <Card
        title={t('networkDetail.title', { network: networkName })}
        extra={
          <Button type="primary" icon={<SearchOutlined />} onClick={handleViewIPs}>
            {t('networkDetail.action.viewIps')}
          </Button>
        }
      >
        {detailData.network_info && (
          <Descriptions size="small" bordered column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label={t('networkList.field.network')}>
              {detailData.network_info.network}
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.ipConfig.subnetMask')}>
              {detailData.network_info.subnet_mask ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('networkDetail.field.gateway')}>
              {detailData.network_info.gateway ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('networkDetail.field.usableIps')}>
              {detailData.network_info.usable_ips ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('networkDetail.field.ipRange')}>
              {detailData.network_info.start_ip} - {detailData.network_info.end_ip}
            </Descriptions.Item>
            <Descriptions.Item label={t('networkList.field.switch')}>
              {detailData.network_info.switch_name ?? '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      {/* 使用率 Card */}
      {usageData && (
        <Card title={t('networkDetail.usage.title')} style={{ marginTop: 16 }}>
          <Row gutter={24} align="middle">
            <Col span={8}>
              <Progress
                type="circle"
                percent={Math.round(usageData.usage_rate * 100)}
                size={120}
                strokeColor={
                  usageData.usage_rate > 0.8
                    ? '#ff4d4f'
                    : usageData.usage_rate > 0.6
                      ? '#faad14'
                      : '#52c41a'
                }
              />
            </Col>
            <Col span={16}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title={t('networkDetail.usage.totalIps')} value={usageData.total_ips} />
                </Col>
                <Col span={8}>
                  <Statistic
                    title={t('networkDetail.usage.usedIps')}
                    value={usageData.used_ips}
                    styles={{ content: { color: '#1890ff' } }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title={t('networkDetail.usage.availableIps')}
                    value={usageData.available_ips}
                    styles={{ content: { color: '#52c41a' } }}
                  />
                </Col>
              </Row>
            </Col>
          </Row>
        </Card>
      )}

      {/* 路由信息 Card */}
      {detailData.network_info_list && detailData.network_info_list.length > 0 && (
        <Card title={t('networkDetail.routeInfo.title')} style={{ marginTop: 16 }}>
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
