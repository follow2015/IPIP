import React, { useMemo, useState } from 'react';
import { Modal, Select, Button, Table, Tag, Alert, Space, Typography, message } from 'antd';
import { NodeIndexOutlined, CheckOutlined } from '@ant-design/icons';
import { useDiscoverTopology, useApplyDiscoveredTopology } from '@/services/topology';
import { useSwitchOptions } from '@/services/switch';
import type {
  TopologyDiscoverySuggestion,
  TopologyDiscoverySwitchResult,
  DiscoveryMatchStatus
} from '@/services/topology';

const { Text } = Typography;

const STATUS_META: Record<DiscoveryMatchStatus, { label: string; color: string }> = {
  existing: { label: '已存在', color: 'green' },
  matched: { label: '可建立', color: 'geekblue' },
  partial: { label: '部分匹配', color: 'orange' },
  unknown_peer: { label: '未知对端', color: 'default' },
  port_occupied: { label: '端口被占用', color: 'volcano' }
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
      message.warning('请先选择要探测的交换机');
      return;
    }
    setSelectedRowKeys([]);
    discoverMutation.mutate(
      { device_ids: selectedSwitchIds },
      {
        onSuccess: (data) => {
          setResults(data.results ?? []);
          if ((data.total_suggestions ?? 0) === 0) {
            message.success('未发现新的邻居建议');
          }
        }
      }
    );
  };

  const handleApply = () => {
    const chosen = matchedRows.filter((r) => selectedRowKeys.includes(r._key));
    if (chosen.length === 0) {
      message.warning('请勾选"可建立"状态的建议');
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
                `已建立 ${created} 条连接` +
                  (skippedCount > 0 ? `，${skippedCount} 条被安全跳过` : '')
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
    { title: '交换机', dataIndex: '_switch_name', width: 110 },
    { title: '本机端口', dataIndex: 'local_port_name', width: 130 },
    {
      title: '对端',
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
    { title: '对端端口', dataIndex: 'peer_port_name', width: 140 },
    {
      title: '协议',
      dataIndex: '_source',
      width: 70,
      render: (s: string) => <Tag style={{ fontSize: 10 }}>{s.toUpperCase()}</Tag>
    },
    {
      title: '状态',
      dataIndex: 'match_status',
      width: 100,
      render: (s: DiscoveryMatchStatus) => {
        const meta = STATUS_META[s] ?? { label: s, color: 'default' };
        return (
          <Tag color={meta.color} style={{ fontSize: 10 }}>
            {meta.label}
          </Tag>
        );
      }
    },
    {
      title: '说明',
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
          LLDP/CDP 拓扑发现
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={860}
      footer={[
        <Button key="cancel" onClick={onClose}>
          关闭
        </Button>,
        <Button
          key="apply"
          type="primary"
          icon={<CheckOutlined />}
          disabled={matchedRows.length === 0}
          onClick={handleApply}
          loading={applyMutation.isPending}
        >
          应用勾选建议{selectedRowKeys.length > 0 ? `（${selectedRowKeys.length}）` : ''}
        </Button>
      ]}
    >
      <Space size={8} style={{ width: '100%' }} direction="vertical">
        <Alert
          type="info"
          showIcon
          message="发现结果仅作建议：只有两端设备与端口全部匹配且端口未被占用的条目才会建立连接，手工录入的连接关系不会被覆盖。"
        />
        <Space.Compact style={{ width: '100%' }}>
          <Select
            mode="multiple"
            allowClear
            placeholder={
              roomId ? '选择本机房要探测的交换机' : '选择要探测的交换机（可先选机房过滤）'
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
            开始发现
          </Button>
        </Space.Compact>

        {hasError && (
          <Alert
            type="warning"
            showIcon
            message="部分交换机探测失败（SSH 超时或无凭据），详见说明列；其余结果不受影响。"
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
          locale={{ emptyText: '选择交换机后点击"开始发现"' }}
        />
      </Space>
    </Modal>
  );
};

export default LldpDiscoveryModal;
