import React, { useMemo, useState } from 'react';
import { Modal, Select, Button, Table, Tag, Alert, Space, Typography } from 'antd';
import { NodeIndexOutlined, CheckOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useDiscoverTopology, useApplyDiscoveredTopology } from '@/services/topology';
import { useResponsive } from '@/hooks/useResponsive';
import { useMessage } from '@/hooks/useMessage';
import { useSwitchOptions } from '@/services/switch';
import type {
  TopologyDiscoverySuggestion,
  TopologyDiscoverySwitchResult,
  DiscoveryMatchStatus
} from '@/services/topology';

const { Text } = Typography;

type DiscoveryStatusKey =
  | 'topology.discovery.status.existing'
  | 'topology.discovery.status.matched'
  | 'topology.discovery.status.partial'
  | 'topology.discovery.status.unknownPeer'
  | 'topology.discovery.status.portOccupied';

const STATUS_COLOR: Record<DiscoveryMatchStatus, string> = {
  existing: 'green',
  matched: 'geekblue',
  partial: 'orange',
  unknown_peer: 'default',
  port_occupied: 'volcano'
};

const STATUS_LABEL_KEY: Record<DiscoveryMatchStatus, DiscoveryStatusKey> = {
  existing: 'topology.discovery.status.existing',
  matched: 'topology.discovery.status.matched',
  partial: 'topology.discovery.status.partial',
  unknown_peer: 'topology.discovery.status.unknownPeer',
  port_occupied: 'topology.discovery.status.portOccupied'
};

interface RowType extends TopologyDiscoverySuggestion {
  _key: string;
  _device_id: number;
  _switch_name: string;
  _source: string;
}

interface LldpDiscoveryModalProps {
  open: boolean;
  onClose: () => void;
  roomId?: number;
}

const LldpDiscoveryModal: React.FC<LldpDiscoveryModalProps> = ({ open, onClose, roomId }) => {
  const message = useMessage();
  const { isMobile } = useResponsive();
  const { t: tn } = useTranslation('network');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const [selectedSwitchIds, setSelectedSwitchIds] = useState<number[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [results, setResults] = useState<TopologyDiscoverySwitchResult[]>([]);

  const { data: switchOptions } = useSwitchOptions(roomId);
  const discoverMutation = useDiscoverTopology();
  const applyMutation = useApplyDiscoveredTopology();

  const rows: RowType[] = useMemo(() => {
    const nameOf = (id: number) => switchOptions?.find((o) => o.value === id)?.label ?? `#${id}`;
    return results.flatMap((r) =>
      (r.suggestions ?? []).map((s, i) => ({
        ...s,
        _key: `${r.device_id}-${i}`,
        _device_id: r.device_id,
        _switch_name: nameOf(r.device_id),
        _source: r.source ?? '-'
      }))
    );
  }, [results, switchOptions]);

  const matchedRows = rows.filter((r) => r.match_status === 'matched');
  const hasError = results.some((r) => r.error);

  const handleDiscover = () => {
    if (selectedSwitchIds.length === 0) {
      message.warning(tn('topology.discovery.selectSwitchFirst'));
      return;
    }
    setSelectedRowKeys([]);
    discoverMutation.mutate(
      { device_ids: selectedSwitchIds },
      {
        onSuccess: (data) => {
          setResults(data.results ?? []);
          if ((data.total_suggestions ?? 0) === 0) {
            message.success(tn('topology.discovery.noSuggestions'));
          }
        }
      }
    );
  };

  const handleApply = () => {
    const chosen = matchedRows.filter((r) => selectedRowKeys.includes(r._key));
    if (chosen.length === 0) {
      message.warning(
        tn('topology.discovery.selectMatchedOnly', {
          status: tn('topology.discovery.status.matched')
        })
      );
      return;
    }
    const byDevice = new Map<number, TopologyDiscoverySuggestion[]>();
    chosen.forEach((r) => {
      const { _key: _k, _device_id: did, _switch_name: _n, _source: _s, ...item } = r;
      byDevice.set(did, [...(byDevice.get(did) ?? []), item]);
    });

    let done = 0;
    const total = byDevice.size;
    let created = 0;
    byDevice.forEach((items, did) => {
      applyMutation.mutate(
        { device_id: did, suggestions: items },
        {
          onSuccess: (res) => {
            created += res.created_count;
            done += 1;
            if (done === total) {
              const skippedCount = chosen.length - created;
              message.success(
                skippedCount > 0
                  ? tn('topology.discovery.createdLinksWithSkipped', {
                      count: created,
                      skipped: skippedCount
                    })
                  : tn('topology.discovery.createdLinks', { count: created })
              );
              onClose();
            }
          },
          onError: () => {
            done += 1;
            if (done === total) onClose();
          }
        }
      );
    });
  };

  const columns = [
    { title: tn('ip.field.switch'), dataIndex: '_switch_name', width: 110 },
    { title: td('connection.column.localPort'), dataIndex: 'local_port_name', width: 130 },
    {
      title: tn('topology.discovery.column.peer'),
      dataIndex: 'peer_name',
      width: 150,
      render: (name: string, r: RowType) => (
        <Space size={4} direction="vertical">
          <span>{name || '-'}</span>
          {r.peer_mgmt_ip && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {r.peer_mgmt_ip}
            </Text>
          )}
        </Space>
      )
    },
    { title: td('connection.column.peerPort'), dataIndex: 'peer_port_name', width: 140 },
    {
      title: td('credential.protocol'),
      dataIndex: '_source',
      width: 70,
      render: (s: string) => <Tag style={{ fontSize: 10 }}>{s.toUpperCase()}</Tag>
    },
    {
      title: tc('field.status'),
      dataIndex: 'match_status',
      width: 100,
      render: (s: DiscoveryMatchStatus) => {
        const key = STATUS_LABEL_KEY[s];
        return (
          <Tag color={STATUS_COLOR[s] ?? 'default'} style={{ fontSize: 10 }}>
            {key ? tn(key) : s}
          </Tag>
        );
      }
    },
    {
      title: tn('topology.discovery.column.reason'),
      dataIndex: 'reason',
      render: (reason: string) => (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {reason}
        </Text>
      )
    }
  ];

  return (
    <Modal
      title={
        <Space size={6}>
          <NodeIndexOutlined />
          {tn('topology.discovery.title')}
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={isMobile ? 'calc(100vw - 24px)' : 860}
      footer={[
        <Button key="cancel" onClick={onClose}>
          {tc('action.close')}
        </Button>,
        <Button
          key="apply"
          type="primary"
          icon={<CheckOutlined />}
          disabled={matchedRows.length === 0}
          onClick={handleApply}
          loading={applyMutation.isPending}
        >
          {selectedRowKeys.length > 0
            ? tn('topology.discovery.applySelectedWithCount', { count: selectedRowKeys.length })
            : tn('topology.discovery.applySelected')}
        </Button>
      ]}
    >
      <Space size={8} style={{ width: '100%' }} direction="vertical">
        <Alert
          type="info"
          showIcon
          message={tn('topology.discovery.notice')}
        />
        <Space.Compact style={{ width: '100%' }}>
          <Select
            mode="multiple"
            allowClear
            placeholder={
              roomId
                ? tn('topology.discovery.selectPlaceholderInRoom')
                : tn('topology.discovery.selectPlaceholder')
            }
            style={{ flex: 1 }}
            maxTagCount={5}
            options={switchOptions ?? []}
            value={selectedSwitchIds}
            onChange={(v) => setSelectedSwitchIds(v)}
          />
          <Button
            type="primary"
            ghost
            icon={<NodeIndexOutlined />}
            onClick={handleDiscover}
            loading={discoverMutation.isPending}
          >
            {tn('topology.discovery.start')}
          </Button>
        </Space.Compact>

        {hasError && (
          <Alert
            type="warning"
            showIcon
            message={tn('topology.discovery.partialFailed')}
          />
        )}

        <Table
          size="small"
          columns={columns}
          dataSource={rows}
          rowKey="_key"
          loading={discoverMutation.isPending}
          pagination={rows.length > 20 ? { pageSize: 20 } : false}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: (r: RowType) => ({
              disabled: r.match_status !== 'matched'
            })
          }}
          locale={{
            emptyText: tn('topology.discovery.emptyText', {
              action: tn('topology.discovery.start')
            })
          }}
          scroll={{ x: 'max-content' }}
        />
      </Space>
    </Modal>
  );
};

export default LldpDiscoveryModal;
