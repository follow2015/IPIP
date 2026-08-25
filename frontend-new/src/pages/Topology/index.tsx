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
import {
  ApartmentOutlined,
  CloudServerOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useNetworkTopology, useDeviceTopology, useAutoDetectTopology } from '@/services/topology';
import { useRoomOptions } from '@/services/room';
import { useVirtualRooms } from '@/services/virtual-room';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import type { LayoutType } from './TopologyGraph';
import TopologyGraph from './TopologyGraph';
import type { TopologyGraphHandle } from './TopologyGraph';
import TopologyToolbar from './TopologyToolbar';
import NodeDetailPanel from './NodeDetailPanel';


type ViewMode = 'network' | 'device';

const TopologyPage: React.FC = () => {
  
  const [viewMode, setViewMode] = useState<ViewMode>('network');
  const [roomId, setRoomId] = useState<number | undefined>(undefined);
  const [virtualRoomId, setVirtualRoomId] = useState<number | undefined>(undefined);
  const [layout, setLayout] = useState<LayoutType>('force');
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [highlightNodeId, setHighlightNodeId] = useState<number | null>(null);
  const [searchValue, setSearchValue] = useState('');
  const deferredSearch = useDeferredValue(searchValue);
  const [autoDetectModalOpen, setAutoDetectModalOpen] = useState(false);
  const graphRef = useRef<TopologyGraphHandle>(null);

  
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
    setDrawerOpen(true);
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
      message.warning('请先选择物理机房（自动推断不支持虚拟机房）');
      return;
    }
    autoDetectMutation.mutate(
      { room_id: roomId, dry_run: true },
      {
        onSuccess: (data) => {
          if (data.changes.length === 0) {
            message.success('未发现需要推断的字段');
          } else {
            setAutoDetectModalOpen(true);
          }
        }
      }
    );
  }, [roomId, autoDetectMutation]);

  const handleApplyAutoDetect = useCallback(() => {
    if (!roomId) return;
    autoDetectMutation.mutate(
      { room_id: roomId, dry_run: false },
      {
        onSuccess: (data) => {
          message.success(`已更新 ${data.changes.length} 条记录`);
          setAutoDetectModalOpen(false);
        }
      }
    );
  }, [roomId, autoDetectMutation]);

  
  const statsItems = useMemo(() => {
    if (!topologyData?.stats) return [];
    const s = topologyData.stats;
    if (viewMode === 'network') {
      return [
        { label: '节点', value: s.total_nodes, icon: <SwapOutlined /> },
        { label: '连接', value: s.total_edges, icon: <ApartmentOutlined /> },
        { label: '核心', value: s.core_count ?? 0, icon: <ThunderboltOutlined /> },
        { label: '接入', value: s.access_count ?? 0, icon: <SwapOutlined /> },
        { label: '在线', value: s.online_count, icon: <CloudServerOutlined /> }
      ];
    }
    return [
      { label: '节点', value: s.total_nodes, icon: <CloudServerOutlined /> },
      { label: '连接', value: s.total_edges, icon: <ApartmentOutlined /> },
      { label: '交换机', value: s.switch_count ?? 0, icon: <SwapOutlined /> },
      { label: '服务器', value: s.server_count ?? 0, icon: <CloudServerOutlined /> },
      { label: '在线', value: s.online_count, icon: <CloudServerOutlined /> }
    ];
  }, [topologyData?.stats, viewMode]);

  
  const autoDetectColumns = [
    { title: '设备', dataIndex: 'device_name', key: 'device_name' },
    {
      title: '变更字段',
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
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {}
      <Card
        size="small"
        style={{ marginBottom: 12, borderRadius: 8 }}
        styles={{ body: { padding: '8px 16px' } }}
      >
        <Row justify="space-between" align="middle">
          <Col>
            <Space size="middle">
              <Radio.Group
                value={viewMode}
                onChange={(e) => setViewMode(e.target.value)}
                optionType="button"
                buttonStyle="solid"
                size="small"
              >
                <Radio.Button value="network">
                  <Space size={4}>
                    <ApartmentOutlined /> 网络拓扑
                  </Space>
                </Radio.Button>
                <Radio.Button value="device">
                  <Space size={4}>
                    <CloudServerOutlined /> 设备拓扑
                  </Space>
                </Radio.Button>
              </Radio.Group>

              <Select
                placeholder="选择机房"
                allowClear
                style={{ width: 200 }}
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
                    label: '物理机房',
                    options: rooms.map((r) => ({ label: r.label, value: `room_${r.value}` }))
                  },
                  {
                    label: '虚拟机房',
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
                刷新
              </Button>
            </Space>
          </Col>

          <Col>
            <Space size="middle">
              {}
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
                icon={<ThunderboltOutlined />}
                onClick={handleAutoDetect}
                loading={autoDetectMutation.isPending}
              >
                自动推断
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {}
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
              <Spin size="large" description="加载拓扑数据..." />
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
              <Empty description="暂无拓扑数据，请确保已配置交换机和连接关系" />
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

      {}
      <NodeDetailPanel
        node={selectedNode}
        edges={topologyData?.edges ?? []}
        nodeMap={nodeMap}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onLocateNode={(nodeId) => setHighlightNodeId(nodeId)}
      />

      {}
      <Modal
        title="自动推断结果预览"
        open={autoDetectModalOpen}
        onCancel={() => setAutoDetectModalOpen(false)}
        width={600}
        footer={[
          <Button key="cancel" onClick={() => setAutoDetectModalOpen(false)}>
            取消
          </Button>,
          <Button
            key="apply"
            type="primary"
            onClick={handleApplyAutoDetect}
            loading={autoDetectMutation.isPending}
          >
            应用变更
          </Button>
        ]}
      >
        <Alert
          type="info"
          showIcon
          message='以下为推断结果预览，点击"应用变更"将写入数据库'
          style={{ marginBottom: 12 }}
        />
        <Table
          size="small"
          columns={autoDetectColumns}
          dataSource={autoDetectMutation.data?.changes ?? []}
          rowKey="device_id"
          pagination={false}
        />
      </Modal>
    </div>
  );
};

export default TopologyPage;
