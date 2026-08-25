import { Button, Tag, Descriptions, Spin, Divider, Modal, Space } from 'antd';
import { EyeOutlined, RedoOutlined, ClearOutlined, DeleteOutlined } from '@ant-design/icons';
import { StatusTag } from '@/components/StatusTag';
import { LINK_STATUS_MAP } from '@/types/enums';
import type { SwitchPort, SwitchPortDetail, SwitchPortIP, PortConfigResult } from '@/types/models';

interface PortDetailModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  port: SwitchPort;
  portDetail?: SwitchPortDetail;
  loadingDetail: boolean;
  portConfig: PortConfigResult | null;
  portType: string;
  onGetConfig: (forceRefresh: boolean) => void;
  getConfigPending: boolean;
  refreshConfigPending: boolean;
  onClearConfig: () => void;
  onDeleteIP: (ipAddress: string, subnetMask: string, isSecondary: boolean) => void;
}


export function PortDetailModal({
  open,
  onClose,
  portName,
  port,
  portDetail,
  loadingDetail,
  portConfig,
  portType,
  onGetConfig,
  getConfigPending,
  refreshConfigPending,
  onClearConfig,
  onDeleteIP
}: PortDetailModalProps) {
  const renderIPList = (ipList: SwitchPortIP[]) => {
    if (!ipList || ipList.length === 0) return <span style={{ color: '#999' }}>-</span>;
    return (
      <div>
        {ipList.map((ip, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
            <Tag color={ip.is_primary ? 'blue' : 'default'} style={{ fontSize: 10, margin: 0 }}>
              {ip.is_primary ? '主' : '从'}
            </Tag>
            <code style={{ fontSize: 12 }}>
              {ip.ip_address}
              {ip.prefix ? `/${ip.prefix}` : ip.subnet_mask ? `/${ip.subnet_mask}` : ''}
            </code>
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() =>
                onDeleteIP(ip.ip_address, ip.subnet_mask || '255.255.255.0', !ip.is_primary)
              }
              style={{ padding: 0, fontSize: 10 }}
            />
          </div>
        ))}
      </div>
    );
  };

  const renderMembers = (members: string[]) => {
    if (!members || members.length === 0)
      return <span style={{ color: '#999' }}>暂无成员端口</span>;
    return (
      <div>
        {members.map((m, i) => (
          <Tag key={i} style={{ marginBottom: 4 }}>
            <code>{m}</code>
          </Tag>
        ))}
      </div>
    );
  };

  return (
    <Modal
      title={<span>端口详情 — {portName}</span>}
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      destroyOnHidden
    >
      {loadingDetail ? (
        <Spin />
      ) : portDetail ? (
        <div>
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="端口号">
              <code>{portName}</code>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <StatusTag
                status={portDetail.status ?? port.link_status}
                statusMap={LINK_STATUS_MAP}
              />
            </Descriptions.Item>
            <Descriptions.Item label="速率">
              {portDetail.speed ?? port.speed ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="VLAN">
              {portDetail.vlan ?? port.vlan ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="MAC">
              {portDetail.port_mac ?? port.mac_address ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="IP地址">{renderIPList(portDetail.ip_list)}</Descriptions.Item>
            <Descriptions.Item label="客户">{port.customer_name ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="描述">
              {port.notes ?? portDetail.description ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间" span={2}>
              {portDetail.updated_at
                ? new Date(portDetail.updated_at).toLocaleString('zh-CN')
                : '-'}
            </Descriptions.Item>
          </Descriptions>

          {portType === 'vlan' &&
            (portDetail?.vlan_ports?.length ?? portConfig?.vlan_ports?.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <h5>VLAN 成员端口</h5>
                {renderMembers(portDetail?.vlan_ports ?? portConfig?.vlan_ports ?? [])}
              </div>
            )}

          {portType === 'trunk' &&
            (portDetail?.trunk_members?.length ?? portConfig?.trunk_members?.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <h5>Trunk 成员端口</h5>
                {renderMembers(portDetail?.trunk_members ?? portConfig?.trunk_members ?? [])}
              </div>
            )}

          <Divider />
          <div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 8
              }}
            >
              <span style={{ fontWeight: 500 }}>端口配置</span>
              <Space size={4}>
                {!portConfig ? (
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => onGetConfig(false)}
                    loading={getConfigPending}
                  >
                    {portDetail?.has_port_config ? '查看配置' : '获取配置'}
                  </Button>
                ) : (
                  <Button
                    size="small"
                    icon={<RedoOutlined />}
                    onClick={() => onGetConfig(true)}
                    loading={refreshConfigPending}
                  >
                    刷新
                  </Button>
                )}
                <Button size="small" icon={<ClearOutlined />} danger onClick={onClearConfig}>
                  清除
                </Button>
              </Space>
            </div>
            {portConfig ? (
              <>
                {portConfig.updated_at && (
                  <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>
                    更新时间：{new Date(portConfig.updated_at).toLocaleString('zh-CN')}
                    {portConfig.from_cache && ' (缓存)'}
                  </div>
                )}
                <pre
                  style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 4,
                    fontSize: 12,
                    maxHeight: 400,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  {portConfig.port_config}
                </pre>
              </>
            ) : portDetail?.has_port_config ? (
              <span style={{ fontSize: 12, color: '#999' }}>
                已有缓存配置（
                {portDetail.port_config_updated_at
                  ? new Date(portDetail.port_config_updated_at).toLocaleString('zh-CN')
                  : '未知时间'}
                ）
              </span>
            ) : (
              <span style={{ fontSize: 12, color: '#999' }}>
                暂无配置数据，点击"获取配置"从设备读取
              </span>
            )}
          </div>
        </div>
      ) : (
        <div>未找到端口详情</div>
      )}
    </Modal>
  );
}

export default PortDetailModal;
