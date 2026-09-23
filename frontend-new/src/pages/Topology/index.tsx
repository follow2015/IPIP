/**
 * 网络拓扑页面
 *
 * 功能：
 * - 网络层拓扑 / 设备层拓扑 视图切换
 * - 机房过滤
 * - G6 图形渲染（布局切换 / 缩放 / 搜索定位）
 * - 节点详情侧边抽屉
 * - 自动推断拓扑字段
 */
import React, { useState, useCallback, useMemo, useRef, useDeferredValue, useEffect } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Select,
  Radio,
  Space,
  Button,
  Statistic,
  Row,
  Col,
  Modal,
  Table,
  Tag,
  message,
  Spin,
  Empty,
  Alert
} from 'antd';
import { useResponsive } from '@/hooks/useResponsive';
import {
  ApartmentOutlined,
  CloudServerOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  NodeIndexOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNetworkTopology, useDeviceTopology, useAutoDetectTopology } from '@/services/topology';
import { useRoomOptions } from '@/services/room';
import { useVirtualRooms } from '@/services/virtual-room';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import type { LayoutType } from './TopologyGraph';
import TopologyGraph from './TopologyGraph';
import type { TopologyGraphHandle } from './TopologyGraph';
import TopologyToolbar from './TopologyToolbar';
import NodeDetailPanel from './NodeDetailPanel';
import LldpDiscoveryModal from './LldpDiscoveryModal';


type ViewMode = 'network' | 'device';

const TopologyPage: React.FC = () => {
  const [viewMode, setViewMode] = useState<ViewMode>('network');
  const [roomId, setRoomId] = useState<number | undefined>(undefined);
  const [virtualRoomId, setVirtualRoomId] = useState<number | undefined>(undefined);
  const [layout, setLayout] = useState<LayoutType>('force');
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const drawer = useDisclosure();
  const [highlightNodeId, setHighlightNodeId] = useState<number | null>(null);
  const [searchValue, setSearchValue] = useState('');
  const deferredSearch = useDeferredValue(searchValue);
  const autoDetectModal = useDisclosure();
  const discoveryModal = useDisclosure();
  const graphRef = useRef<TopologyGraphHandle>(null);
  const { isMobile } = useResponsive();
  const { t: tn } = useTranslation('network');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');

  const { data: roomOptions } = useRoomOptions();
  const { data: virtualRoomsData } = useVirtualRooms({ per_page: 200 });
  const networkQuery = useNetworkTopology(
    viewMode === 'network' ? { room_id: roomId, virtual_room_id: virtualRoomId } : undefined
  );
  const deviceQuery = useDeviceTopology(
    viewMode === 'device' ? { room_id: roomId, virtual_room_id: virtualRoomId } : undefined
  );
  const autoDetectMutation = useAutoDetectTopology();

  const topologyData = viewMode === 'network' ? networkQuery.data : deviceQuery.data;
  const isLoading = viewMode === 'network' ? networkQuery.isLoading : deviceQuery.isLoading;

  const rooms = roomOptions ?? [];
  const virtualRooms = virtualRoomsData?.items ?? [];

  const nodeMap = useMemo(
    () => Object.fromEntries((topologyData?.nodes ?? []).map((n) => [n.id, n])),
    [topologyData]
  );

  const handleNodeClick = useCallback((node: TopologyNode) => {
    setSelectedNode(node);
    drawer.open();
  }, []);

  const handleEdgeClick = useCallback((_edge: TopologyEdge) => {
  }, []);

  useEffect(() => {
    if (!deferredSearch.trim()) {
      setHighlightNodeId(null);
      return;
    }
    const matched = topologyData?.nodes.find((n) =>
      n.name.toLowerCase().includes(deferredSearch.toLowerCase())
    );
    setHighlightNodeId(matched ? matched.id : null);
  }, [deferredSearch, topologyData?.nodes]);

  const handleSearch = useCallback((value: string) => {
    setSearchValue(value);
  }, []);

  const handleAutoDetect = useCallback(() => {
    if (!roomId) {
      message.warning(tn('topology.autoDetect.needPhysicalRoom'));
      return;
    }
    autoDetectMutation.mutate(
      { room_id: roomId, dry_run: true },
      {
        onSuccess: (data) => {
          if (data.changes.length === 0) {
            message.success(tn('topology.autoDetect.noChanges'));
          } else {
            autoDetectModal.open();
          }
        }
      }
    );
  }, [roomId, autoDetectMutation, tn]);

  const handleApplyAutoDetect = useCallback(() => {
    if (!roomId) return;
    autoDetectMutation.mutate(
      { room_id: roomId, dry_run: false },
      {
        onSuccess: (data) => {
          message.success(tn('topology.autoDetect.updatedRecords', { count: data.changes.length }));
          autoDetectModal.close();
        }
      }
    );
  }, [roomId, autoDetectMutation, tn]);

  const statsItems = useMemo(() => {
    if (!topologyData?.stats) return [];
    const s = topologyData.stats;
    if (viewMode === 'network') {
      return [
        { label: tn('topology.stats.node'), value: s.total_nodes, icon: <SwapOutlined /> },
        { label: tn('topology.stats.link'), value: s.total_edges, icon: <ApartmentOutlined /> },
        {
          label: td('form.networkTopology.roleOption.core'),
          value: s.core_count ?? 0,
          icon: <ThunderboltOutlined />
        },
        {
          label: td('form.networkTopology.roleOption.access'),
          value: s.access_count ?? 0,
          icon: <SwapOutlined />
        },
        { label: td('status.ONLINE'), value: s.online_count, icon: <CloudServerOutlined /> }
      ];
    }
    return [
      { label: tn('topology.stats.node'), value: s.total_nodes, icon: <CloudServerOutlined /> },
      { label: tn('topology.stats.link'), value: s.total_edges, icon: <ApartmentOutlined /> },
      { label: tn('ip.field.switch'), value: s.switch_count ?? 0, icon: <SwapOutlined /> },
      { label: td('deviceType.SERVER'), value: s.server_count ?? 0, icon: <CloudServerOutlined /> },
      { label: td('status.ONLINE'), value: s.online_count, icon: <CloudServerOutlined /> }
    ];
  }, [topologyData?.stats, viewMode, tn, td]);

  const autoDetectColumns = [
    { title: tn('topology.autoDetect.column.device'), dataIndex: 'device_name', key: 'device_name' },
    {
      title: tn('topology.autoDetect.column.changedFields'),
      dataIndex: 'fields',
      key: 'fields',
      render: (fields: Record<string, { old: unknown; new: unknown }>) => (
        <Space orientation="vertical" size={2}>
          {Object.entries(fields).map(([key, val]) => (
            <span key={key} style={{ fontSize: 12 }}>
              <Tag color="orange" style={{ fontSize: 10 }}>
                {key}
              </Tag>
              {String(val.old ?? '-')} → {String(val.new ?? '-')}
            </span>
          ))}
        </Space>
      )
    }
  ];

  return (
    <div
      style={{
        padding: isMobile ? 12 : 16,
        height: '100%',
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      {/* 顶部控制栏 */}
      <Card
        size="small"
        style={{ marginBottom: 12, borderRadius: 8 }}
        styles={{ body: { padding: isMobile ? '8px 12px' : '8px 16px' } }}
      >
        <Row justify="space-between" align="middle" gutter={[8, 8]}>
          <Col xs={24} md="auto">
            <Space size="middle" wrap>
              <Radio.Group
                value={viewMode}
                onChange={(e) => setViewMode(e.target.value)}
                optionType="button"
                buttonStyle="solid"
                size="small"
              >
                <Radio.Button value="network">
                  <Space size={4}>
                    <ApartmentOutlined /> {tn('topology.view.network')}
                  </Space>
                </Radio.Button>
                <Radio.Button value="device">
                  <Space size={4}>
                    <CloudServerOutlined /> {tn('topology.view.device')}
                  </Space>
                </Radio.Button>
              </Radio.Group>

              <Select
                placeholder={tn('topology.filter.roomPlaceholder')}
                allowClear
                style={{ width: isMobile ? '100%' : 200 }}
                size="small"
                value={
                  virtualRoomId ? `vr_${virtualRoomId}` : roomId ? `room_${roomId}` : undefined
                }
                onChange={(val: string | undefined) => {
                  if (!val) {
                    setRoomId(undefined);
                    setVirtualRoomId(undefined);
                  } else if (val.startsWith('vr_')) {
                    setVirtualRoomId(Number(val.slice(3)));
                    setRoomId(undefined);
                  } else if (val.startsWith('room_')) {
                    setRoomId(Number(val.slice(5)));
                    setVirtualRoomId(undefined);
                  }
                }}
                options={[
                  {
                    label: tn('topology.filter.groupPhysicalRoom'),
                    options: rooms.map((r) => ({ label: r.label, value: `room_${r.value}` }))
                  },
                  {
                    label: tn('topology.filter.groupVirtualRoom'),
                    options: virtualRooms.map((vr) => ({ label: vr.name, value: `vr_${vr.id}` }))
                  }
                ]}
              />

              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => {
                  if (viewMode === 'network') networkQuery.refetch();
                  else deviceQuery.refetch();
                }}
                loading={isLoading}
              >
                {tc('action.refresh')}
              </Button>
            </Space>
          </Col>

          <Col xs={24} md="auto">
            <Space size="middle" wrap>
              {/* 统计 */}
              {statsItems.map((item) => (
                <Statistic
                  key={item.label}
                  title={item.label}
                  value={item.value}
                  prefix={item.icon}
                  styles={{ content: { fontSize: 14 } }}
                  style={{ marginRight: 0 }}
                />
              ))}

              <Button
                size="small"
                type="primary"
                ghost
                icon={<NodeIndexOutlined />}
                onClick={() => discoveryModal.open()}
              >
                {tn('topology.action.lldpDiscovery')}
              </Button>
              <Button
                size="small"
                type="primary"
                ghost
                icon={<ThunderboltOutlined />}
                onClick={handleAutoDetect}
                loading={autoDetectMutation.isPending}
              >
                {tn('topology.action.autoDetect')}
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 图形区域 */}
      <Card
        size="small"
        style={{
          flex: 1,
          borderRadius: 8,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
        styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 0 } }}
      >
        <TopologyToolbar
          layout={layout}
          onLayoutChange={setLayout}
          onZoomIn={() => graphRef.current?.zoomIn()}
          onZoomOut={() => graphRef.current?.zoomOut()}
          onFitView={() => graphRef.current?.fitView()}
          onSearch={handleSearch}
        />

        {isMobile && (
          <Alert
            banner
            type="info"
            showIcon
            message={tn('topology.mobileHint')}
            style={{ fontSize: 12 }}
          />
        )}

        <div style={{ flex: 1, position: 'relative' }}>
          {isLoading && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 10,
                background: 'rgba(255,255,255,0.7)'
              }}
            >
              <Spin size="large" description={tn('topology.loading')} />
            </div>
          )}

          {!isLoading && !topologyData?.nodes?.length && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <Empty description={tn('topology.empty')} />
            </div>
          )}

          {topologyData && topologyData.nodes.length > 0 && (
            <TopologyGraph
              ref={graphRef}
              nodes={topologyData.nodes}
              edges={topologyData.edges}
              layout={layout}
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
              highlightNodeId={highlightNodeId}
            />
          )}
        </div>
      </Card>

      {/* 节点详情抽屉 */}
      <NodeDetailPanel
        node={selectedNode}
        edges={topologyData?.edges ?? []}
        nodeMap={nodeMap}
        open={drawer.isOpen}
        onClose={() => drawer.close()}
        onLocateNode={(nodeId) => setHighlightNodeId(nodeId)}
      />

      {/* LLDP/CDP 发现 Modal（建议式，不自动覆盖） */}
      <LldpDiscoveryModal
        open={discoveryModal.isOpen}
        onClose={() => discoveryModal.close()}
        roomId={roomId}
      />

      {/* 自动推断预览 Modal */}
      <Modal
        title={tn('topology.autoDetect.previewTitle')}
        open={autoDetectModal.isOpen}
        onCancel={() => autoDetectModal.close()}
        width={isMobile ? 'calc(100vw - 24px)' : 600}
        footer={[
          <Button key="cancel" onClick={() => autoDetectModal.close()}>
            {tc('action.cancel')}
          </Button>,
          <Button
            key="apply"
            type="primary"
            onClick={handleApplyAutoDetect}
            loading={autoDetectMutation.isPending}
          >
            {tn('topology.autoDetect.applyChanges')}
          </Button>
        ]}
      >
        <Alert
          type="info"
          showIcon
          message={tn('topology.autoDetect.previewAlert', {
            action: tn('topology.autoDetect.applyChanges')
          })}
          style={{ marginBottom: 12 }}
        />
        <Table
          size="small"
          columns={autoDetectColumns}
          dataSource={autoDetectMutation.data?.changes ?? []}
          rowKey="device_id"
          pagination={false}
          scroll={{ x: 'max-content' }}
        />
      </Modal>
    </div>
  );
};

export default TopologyPage;
