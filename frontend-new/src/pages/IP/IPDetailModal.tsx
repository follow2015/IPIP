import { Modal, Descriptions, Spin, Tag } from 'antd';
import type { IPAddress } from '@/types/models';
import { IP_STATUS_MAP, IPStatusCode } from '@/types/enums';

interface IPDetailModalProps {
  open: boolean;
  onClose: () => void;
  detailAddress: string;
  loading: boolean;
  detail?: IPAddress;
}

export function IPDetailModal({
  open,
  onClose,
  detailAddress,
  loading,
  detail
}: IPDetailModalProps) {
  return (
    <Modal
      title={`IP 详情 - ${detailAddress}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      {loading ? (
        <Spin />
      ) : detail ? (
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="IP地址">{detail.ip_address}</Descriptions.Item>
          <Descriptions.Item label="状态">
            {(() => {
              const s = IP_STATUS_MAP[detail.status as IPStatusCode];
              return <Tag color={s?.color}>{s?.label ?? '未知'}</Tag>;
            })()}
          </Descriptions.Item>
          <Descriptions.Item label="MAC地址">
            {detail.mac_address === 'N/A' ? '-' : detail.mac_address}
          </Descriptions.Item>
          <Descriptions.Item label="交换机">{detail.switch_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="端口">{detail.port ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="机房">{detail.room_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="客户">{detail.customer_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="备注">{detail.notes ?? '-'}</Descriptions.Item>
        </Descriptions>
      ) : (
        <div>未找到详情</div>
      )}
    </Modal>
  );
}
