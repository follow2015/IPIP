/**
 * 节点详情侧边抽屉
 */
import React from 'react';
import { Drawer, Descriptions, Tag, Space, Button } from 'antd';
import { CloudServerOutlined, SwapOutlined, LinkOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { StatusTag } from '@/components/StatusTag';
import { SWITCH_ROLE_MAP, NODE_STATUS_MAP } from '@/types/enums';
import type { TopologyNode, TopologyEdge } from '@/types/models';

interface NodeDetailPanelProps {
  node: TopologyNode | null;
  edges: TopologyEdge[];
  nodeMap: Record<number, TopologyNode>;
  open: boolean;
  onClose: () => void;
  onLocateNode?: (nodeId: number) => void;
}

const NodeDetailPanel: React.FC<NodeDetailPanelProps> = ({
  node,
  edges,
  nodeMap,
  open,
  onClose,
  onLocateNode
}) => {
  const navigate = useNavigate();

  if (!node) return null;

  const connectedEdges = edges.filter((e) => e.source === node.id || e.target === node.id);

  const handleNavigate = () => {
    if (node.device_type === 'network') {
      navigate(`/switches/${node.id}`);
    } else {
      navigate(`/devices/${node.id}`);
    }
  };

  return (
    <Drawer
      title={
        <Space>
          {node.device_type === 'network' ? <SwapOutlined /> : <CloudServerOutlined />}
          {node.name}
        </Space>
      }
      placement="right"
      width={360}
      open={open}
      onClose={onClose}
      extra={
        <Button type="link" icon={<LinkOutlined />} onClick={handleNavigate}>
          查看详情
        </Button>
      }
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="设备类型">
          {node.device_type === 'network' ? '网络设备' : '服务器'}
        </Descriptions.Item>
        <Descriptions.Item label="IP 地址">{node.ip ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <StatusTag status={node.status} statusMap={NODE_STATUS_MAP} />
        </Descriptions.Item>
        {node.device_type === 'network' && (
          <>
            <Descriptions.Item label="角色">
              <StatusTag status={node.switch_role} statusMap={SWITCH_ROLE_MAP} />
            </Descriptions.Item>
            <Descriptions.Item label="层级">
              {node.layer != null ? `L${node.layer}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="端口数">{node.port_num ?? '-'}</Descriptions.Item>
          </>
        )}
        <Descriptions.Item label="机房">{node.room_name ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="机柜">{node.cabinet_name ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="连接数">{connectedEdges.length}</Descriptions.Item>
      </Descriptions>

      {connectedEdges.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ marginBottom: 8 }}>连接列表</h4>
          {connectedEdges.map((edge) => {
            const isSource = edge.source === node.id;
            const peerId = isSource ? edge.target : edge.source;
            const localPort = isSource ? edge.local_port : edge.peer_port;
            const peerPort = isSource ? edge.peer_port : edge.local_port;
            const edgeTypeLabel =
              edge.edge_type === 'n2n'
                ? 'N2N'
                : edge.edge_type === 'd2n'
                  ? 'D2N'
                  : edge.edge_type === 'uplink'
                    ? '上行'
                    : edge.edge_type;

            return (
              <div
                key={edge.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '4px 8px',
                  marginBottom: 4,
                  background: '#fafafa',
                  borderRadius: 4,
                  fontSize: 12
                }}
              >
                <Space size={4}>
                  <Tag
                    color={
                      edge.edge_type === 'n2n'
                        ? 'green'
                        : edge.edge_type === 'uplink'
                          ? 'blue'
                          : 'orange'
                    }
                    style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}
                  >
                    {edgeTypeLabel}
                  </Tag>
                  {onLocateNode ? (
                    <Button
                      type="link"
                      size="small"
                      style={{ padding: 0, height: 'auto', fontSize: 12 }}
                      onClick={() => onLocateNode(peerId)}
                    >
                      → {nodeMap[peerId]?.name ?? `设备 ${peerId}`}
                    </Button>
                  ) : (
                    <span>→ {nodeMap[peerId]?.name ?? `设备 ${peerId}`}</span>
                  )}
                  {peerPort && <span style={{ color: '#8c8c8c', marginLeft: 4 }}>:{peerPort}</span>}
                </Space>
                <span style={{ color: '#999' }}>{edge.bandwidth ?? '-'}</span>
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
};

export default NodeDetailPanel;
