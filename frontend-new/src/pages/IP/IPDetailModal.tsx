import { Modal, Descriptions, Spin, Tag } from 'antd';
import type { IPAddress } from '@/types/models';
import { getIPStatusMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

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
  const { t: td } = useTranslation('device');
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  return (
    <Modal
      title={t('ip.detail.title', { address: detailAddress })}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      {loading ? (
        <Spin />
      ) : detail ? (
        <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label={t('ip.field.ipAddress')}>
            {detail.ip_address}
          </Descriptions.Item>
          <Descriptions.Item label={t('ip.field.status')}>
            {(() => {
              const s = getIPStatusMeta(detail.status, td);
              return <Tag color={s?.color}>{s?.label ?? tc('field.unknown')}</Tag>;
            })()}
          </Descriptions.Item>
          <Descriptions.Item label={t('ip.field.macAddress')}>
            {detail.mac_address === 'N/A' ? '-' : detail.mac_address}
          </Descriptions.Item>
          <Descriptions.Item label={t('ip.field.switch')}>
            {detail.switch_name ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('ip.field.port')}>{detail.port ?? '-'}</Descriptions.Item>
          <Descriptions.Item label={t('ip.field.room')}>{detail.room_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label={t('ip.field.customer')}>
            {detail.customer_name ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('ip.field.notes')}>{detail.notes ?? '-'}</Descriptions.Item>
        </Descriptions>
      ) : (
        <div>{t('ip.detail.notFound')}</div>
      )}
    </Modal>
  );
}
