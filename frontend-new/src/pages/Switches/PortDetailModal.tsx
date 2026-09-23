import { Button, Tag, Descriptions, Spin, Divider, Modal, Space } from 'antd';
import { EyeOutlined, RedoOutlined, ClearOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { StatusTag } from '@/components/StatusTag';
import { LINK_STATUS_MAP } from '@/types/enums';
import type { SwitchPort, SwitchPortDetail, SwitchPortIP, PortConfigResult } from '@/types/models';
import { formatDateTime } from '@/utils/format';

interface PortDetailModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  port: SwitchPort;
  portDetail?: SwitchPortDetail | null;
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
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const renderIPList = (ipList: SwitchPortIP[]) => {
    if (!ipList || ipList.length === 0) return <span style={{ color: '#999' }}>-</span>;
    return (
      <div>
        {ipList.map((ip, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
            <Tag color={ip.is_primary ? 'blue' : 'default'} style={{ fontSize: 10, margin: 0 }}>
              {ip.is_primary ? td('port.ipRole.primary') : td('port.ipRole.secondary')}
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
      return <span style={{ color: '#999' }}>{td('switch.portDetail.noMembers')}</span>;
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
      title={<span>{td('switch.portDetail.title', { name: portName })}</span>}
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
          <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label={td('switch.portDetail.portNumber')}>
              <code>{portName}</code>
            </Descriptions.Item>
            <Descriptions.Item label={tc('field.status')}>
              <StatusTag
                status={portDetail.status ?? port.link_status}
                statusMap={LINK_STATUS_MAP}
              />
            </Descriptions.Item>
            <Descriptions.Item label={td('switch.portDetail.speed')}>
              {portDetail.speed ?? port.speed ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="VLAN">
              {portDetail.vlan ?? port.vlan ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="MAC">
              {portDetail.port_mac ?? port.mac_address ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={td('port.column.ipAddress')}>
              {renderIPList(portDetail.ip_list)}
            </Descriptions.Item>
            <Descriptions.Item label={tc('field.customer')}>
              {port.customer_name ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={tc('field.description')}>
              {port.notes ?? portDetail.description ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label={tc('field.updatedAt')} span={2}>
              {portDetail.updated_at ? formatDateTime(portDetail.updated_at) : '-'}
            </Descriptions.Item>
          </Descriptions>

          {portType === 'vlan' &&
            (portDetail?.vlan_ports?.length ?? portConfig?.vlan_ports?.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <h5>{td('switch.portDetail.vlanMembers')}</h5>
                {renderMembers(portDetail?.vlan_ports ?? portConfig?.vlan_ports ?? [])}
              </div>
            )}

          {portType === 'trunk' &&
            (portDetail?.trunk_members?.length ?? portConfig?.trunk_members?.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <h5>{td('switch.portDetail.trunkMembers')}</h5>
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
              <span style={{ fontWeight: 500 }}>{td('switch.portDetail.configTitle')}</span>
              <Space size={4}>
                {!portConfig ? (
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => onGetConfig(false)}
                    loading={getConfigPending}
                  >
                    {portDetail?.has_port_config
                      ? td('switch.portDetail.viewConfig')
                      : td('switch.portDetail.fetchConfig')}
                  </Button>
                ) : (
                  <Button
                    size="small"
                    icon={<RedoOutlined />}
                    onClick={() => onGetConfig(true)}
                    loading={refreshConfigPending}
                  >
                    {tc('action.refresh')}
                  </Button>
                )}
                <Button size="small" icon={<ClearOutlined />} danger onClick={onClearConfig}>
                  {td('switch.portDetail.clear')}
                </Button>
              </Space>
            </div>
            {portConfig ? (
              <>
                {portConfig.updated_at && (
                  <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>
                    {tc('field.updatedAt')}：{formatDateTime(portConfig.updated_at)}
                    {portConfig.from_cache && td('switch.portDetail.cached')}
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
                {td('switch.portDetail.cachedConfig', {
                  time: portDetail.port_config_updated_at
                    ? formatDateTime(portDetail.port_config_updated_at)
                    : td('switch.portDetail.unknownTime')
                })}
              </span>
            ) : (
              <span style={{ fontSize: 12, color: '#999' }}>
                {td('switch.portDetail.noConfig')}
              </span>
            )}
          </div>
        </div>
      ) : (
        <div>{td('switch.portDetail.notFound')}</div>
      )}
    </Modal>
  );
}

export default PortDetailModal;
