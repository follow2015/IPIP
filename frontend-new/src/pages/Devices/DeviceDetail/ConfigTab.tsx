/**
 * 设备配置管理组件（嵌入设备详情页）
 * - 接收 deviceId prop
 * - 两个子 Tab：配置备份列表 + 配置变更审批
 * - 备份列表：时间、类型、文件大小、操作（查看/对比）
 * - 变更列表：时间、摘要、状态、操作（审批）
 * - 顶部：触发备份按钮
 */
import { useState } from 'react';
import { Tabs, Table, Button, Space, Tag, Modal, Popconfirm } from 'antd';
import { PlusOutlined, EyeOutlined, SwapOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import {
  useDeviceConfigHistory,
  useDeviceConfigChanges,
  useBackupDeviceConfig,
  useApproveConfigChange,
} from '@/services/deviceConfig';
import type { DeviceConfigBackup, DeviceConfigChange } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';

const BACKUP_TYPE_MAP: Record<string, { label: string; color: string }> = {
  manual: { label: '手动', color: 'blue' },
  scheduled: { label: '定时', color: 'green' },
  pre_change: { label: '变更前', color: 'orange' },
};

const CHANGE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending: { label: '待审批', color: 'orange' },
  approved: { label: '已批准', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
  applied: { label: '已应用', color: 'blue' },
};

interface ConfigTabProps {
  deviceId: number;
}

function ConfigTab({ deviceId }: ConfigTabProps) {
  const message = useMessage();
  const [viewContent, setViewContent] = useState<string | null>(null);
  const [diffContent, setDiffContent] = useState<{ old: string; new: string } | null>(null);

  const { data: backups, isLoading: loadingBackups, refetch: refetchBackups } = useDeviceConfigHistory(deviceId);
  const { data: changes, isLoading: loadingChanges, refetch: refetchChanges } = useDeviceConfigChanges(deviceId);
  const backupConfig = useBackupDeviceConfig();
  const approveChange = useApproveConfigChange();

  const handleBackup = async () => {
    try {
      await backupConfig.mutateAsync(deviceId);
      message.info('配置备份已提交，完成后将通过消息通知您');
      refetchBackups();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '备份失败');
    }
  };

  const handleView = (record: DeviceConfigBackup) => {
    setViewContent(record.config_content);
  };

  const handleDiff = (record: DeviceConfigBackup) => {
    const latest = (backups ?? [])[0];
    if (latest && latest.id !== record.id) {
      setDiffContent({ old: latest.config_content, new: record.config_content });
    } else {
      message.info('没有可对比的配置');
    }
  };

  const handleApprove = async (record: DeviceConfigChange, action: 'approve' | 'reject') => {
    try {
      await approveChange.mutateAsync({ deviceId, changeId: record.id, action });
      message.success(action === 'approve' ? '已批准' : '已拒绝');
      refetchChanges();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const backupColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '类型',
      dataIndex: 'backup_type',
      key: 'backup_type',
      width: 100,
      render: (v: string) => {
        const info = BACKUP_TYPE_MAP[v];
        return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: '文件大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (v: number | null) => v ? `${(v / 1024).toFixed(1)} KB` : '-',
    },
    {
      title: '配置哈希',
      dataIndex: 'config_hash',
      key: 'config_hash',
      width: 120,
      render: (v: string) => v ? v.slice(0, 12) + '...' : '-',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, r: DeviceConfigBackup) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(r)}>查看</Button>
          <Button type="link" size="small" icon={<SwapOutlined />} onClick={() => handleDiff(r)}>对比</Button>
        </Space>
      ),
    },
  ];

  const changeColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '摘要',
      dataIndex: 'change_summary',
      key: 'change_summary',
      render: (v: string) => v || '-',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => {
        const info = CHANGE_STATUS_MAP[v];
        return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, r: DeviceConfigChange) => (
        <Space>
          {r.status === 'pending' && (
            <>
              <Popconfirm title="确定批准此变更？" onConfirm={() => handleApprove(r, 'approve')}>
                <Button type="link" size="small" icon={<CheckOutlined />} style={{ color: '#52c41a' }}>批准</Button>
              </Popconfirm>
              <Popconfirm title="确定拒绝此变更？" onConfirm={() => handleApprove(r, 'reject')}>
                <Button type="link" size="small" danger icon={<CloseOutlined />}>拒绝</Button>
              </Popconfirm>
            </>
          )}
          {r.status === 'approved' && <Tag color="green">已批准</Tag>}
          {r.status === 'rejected' && <Tag color="red">已拒绝</Tag>}
          {r.status === 'applied' && <Tag color="blue">已应用</Tag>}
          {r.status === 'draft' && <Tag>草稿</Tag>}
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'backups',
      label: '配置备份',
      children: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleBackup} loading={backupConfig.isPending}>
              触发备份
            </Button>
          </div>
          <Table<DeviceConfigBackup>
            columns={backupColumns}
            dataSource={backups ?? []}
            loading={loadingBackups}
            rowKey="id"
            size="small"
          />
        </div>
      ),
    },
    {
      key: 'changes',
      label: '配置变更审批',
      children: (
        <Table<DeviceConfigChange>
          columns={changeColumns}
          dataSource={changes ?? []}
          loading={loadingChanges}
          rowKey="id"
          size="small"
        />
      ),
    },
  ];

  return (
    <div>
      <Tabs items={tabItems} />

      {/* 查看配置内容弹窗 */}
      <Modal
        title="配置内容"
        open={viewContent !== null}
        onCancel={() => setViewContent(null)}
        footer={null}
        width={720}
      >
        <pre style={{ maxHeight: 500, overflow: 'auto', fontSize: 12, background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
          {viewContent}
        </pre>
      </Modal>

      {/* 配置对比弹窗 */}
      <Modal
        title="配置对比"
        open={diffContent !== null}
        onCancel={() => setDiffContent(null)}
        footer={null}
        width={900}
      >
        {diffContent && (
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <h4 style={{ marginBottom: 8 }}>旧配置</h4>
              <pre style={{ maxHeight: 500, overflow: 'auto', fontSize: 12, background: '#fff1f0', padding: 12, borderRadius: 4 }}>
                {diffContent.old}
              </pre>
            </div>
            <div style={{ flex: 1 }}>
              <h4 style={{ marginBottom: 8 }}>新配置</h4>
              <pre style={{ maxHeight: 500, overflow: 'auto', fontSize: 12, background: '#f6ffed', padding: 12, borderRadius: 4 }}>
                {diffContent.new}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default ConfigTab;
