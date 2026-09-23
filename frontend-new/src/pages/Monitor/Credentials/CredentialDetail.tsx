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
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;

interface CredentialDetailProps {
  selectedCred: MonitorCredentialListItem | undefined;
  onOpenLink: () => void;
}

export default function CredentialDetail({ selectedCred, onOpenLink }: CredentialDetailProps) {
  const navigate = useNavigate();
  const msg = useMessage();
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
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
      msg.success(t('credential.message.unlinked'));
    } catch (err) {
      msg.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const linkedColumns = [
    {
      title: td('field.name'),
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: LinkedDevice) => (
        <a onClick={() => navigate(`/devices/${record.device_id}`)}>{name}</a>
      )
    },
    {
      title: tc('field.type'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (deviceType: string) => <Tag>{deviceType}</Tag>
    },
    {
      title: t('column.managementIp'),
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      render: (ip: string | null) => ip || '—'
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 160,
      render: (_: unknown, record: LinkedDevice) => (
        <Space size="small">
          <Tooltip title={t('alerts.viewTrend')}>
            <Button
              size="small"
              icon={<LineChartOutlined />}
              onClick={() => navigate(`/monitor/history?deviceId=${record.device_id}`)}
            />
          </Tooltip>
          <ConfirmButton
            size="small"
            icon={<DisconnectOutlined />}
            title={t('credential.confirm.unlinkTitle')}
            content={t('credential.confirm.unlinkContent')}
            okType="danger"
            onConfirm={() => handleUnlink(record.device_id)}
          >
            {td('credential.unlink')}
          </ConfirmButton>
        </Space>
      )
    }
  ];

  if (!selectedCred) {
    return (
      <Card>
        <Empty
          description={t('credential.detail.selectHint')}
          style={{ padding: '60px 0' }}
        />
      </Card>
    );
  }

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size={16}>
      {/* 凭据详情卡片 */}
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
          <Col xs={24} md={8}>
            <Text type="secondary">{tc('field.status')}</Text>
            <div>
              {selectedCred.enabled ? (
                <Tag color="green">{t('credential.status.enabled')}</Tag>
              ) : (
                <Tag>{t('credential.status.disabled')}</Tag>
              )}
            </div>
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">{t('credential.column.linkedDevices')}</Text>
            <div>
              <Text strong style={{ fontSize: 18 }}>
                {selectedCred.linked_count ?? 0}
              </Text>{' '}
              {t('stat.unitDevice', { count: selectedCred.linked_count ?? 0 })}
            </div>
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">{t('credential.detail.id')}</Text>
            <div>
              <Text code>{selectedCred.id}</Text>
            </div>
          </Col>
        </Row>
      </Card>

      {/* 关联设备表 */}
      <Card
        title={t('credential.column.linkedDevices')}
        extra={
          <Button type="primary" icon={<LinkOutlined />} onClick={onOpenLink}>
            {t('credential.column.linkedDevices')}
          </Button>
        }
      >
        <Input
          placeholder={t('credential.searchDevicePlaceholder')}
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
          emptyText={
            deviceSearchKeyword
              ? td('addModal.clone.noMatchDevice')
              : t('credential.message.linkedEmpty')
          }
          searchable={false}
          showCard={false}
          tableProps={linkedTable}
        />
      </Card>
    </Space>
  );
}
