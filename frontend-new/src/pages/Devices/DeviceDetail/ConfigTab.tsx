/**
 * 设备配置管理组件（嵌入设备详情页）
 * - 接收 deviceId prop
 * - 两个子 Tab：配置备份列表 + 配置变更审批
 * - 备份列表：时间、类型、文件大小、操作（查看/对比）
 * - 变更列表：时间、摘要、状态、操作（审批）
 * - 顶部：触发备份按钮
 */
import { useState } from 'react';
import { useConfirm } from '@/utils/confirm';
import { Tabs, Button, Space, Tag, Modal } from 'antd';
import DataTable, { DENSE_PAGINATION } from '@/components/DataTable';
import {
  PlusOutlined,
  EyeOutlined,
  SwapOutlined,
  CheckOutlined,
  CloseOutlined
} from '@ant-design/icons';
import {
  useDeviceConfigHistory,
  useDeviceConfigChanges,
  useBackupDeviceConfig,
  useApproveConfigChange
} from '@/services/deviceConfig';
import type { DeviceConfigBackup, DeviceConfigChange } from '@/types/models';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';

type BackupTypeKey = 'config.backupType.manual' | 'config.backupType.scheduled' | 'config.backupType.preChange';

type ChangeStatusKey =
  | 'config.changeStatus.draft'
  | 'config.changeStatus.pending'
  | 'config.changeStatus.approved'
  | 'config.changeStatus.rejected'
  | 'config.changeStatus.applied';

const BACKUP_TYPE_MAP: Record<string, { labelKey: BackupTypeKey; color: string }> = {
  manual: { labelKey: 'config.backupType.manual', color: 'blue' },
  scheduled: { labelKey: 'config.backupType.scheduled', color: 'green' },
  pre_change: { labelKey: 'config.backupType.preChange', color: 'orange' }
};

const CHANGE_STATUS_MAP: Record<string, { labelKey: ChangeStatusKey; color: string }> = {
  draft: { labelKey: 'config.changeStatus.draft', color: 'default' },
  pending: { labelKey: 'config.changeStatus.pending', color: 'orange' },
  approved: { labelKey: 'config.changeStatus.approved', color: 'green' },
  rejected: { labelKey: 'config.changeStatus.rejected', color: 'red' },
  applied: { labelKey: 'config.changeStatus.applied', color: 'blue' }
};

interface ConfigTabProps {
  deviceId: number;
}

function ConfigTab({ deviceId }: ConfigTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const message = useMessage();
  const [viewContent, setViewContent] = useState<string | null>(null);
  const [diffContent, setDiffContent] = useState<{ old: string; new: string } | null>(null);

  const {
    data: backups,
    isLoading: loadingBackups,
    refetch: refetchBackups
  } = useDeviceConfigHistory(deviceId);
  const {
    data: changes,
    isLoading: loadingChanges,
    refetch: refetchChanges
  } = useDeviceConfigChanges(deviceId);
  const backupConfig = useBackupDeviceConfig();
  const approveChange = useApproveConfigChange();

  const handleBackup = async () => {
    try {
      await backupConfig.mutateAsync(deviceId);
      message.info(t('config.message.backupSubmitted'));
      refetchBackups();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('config.message.backupFailed'));
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
      message.info(t('config.message.noDiff'));
    }
  };

  const handleApprove = async (record: DeviceConfigChange, action: 'approve' | 'reject') => {
    try {
      await approveChange.mutateAsync({ deviceId, changeId: record.id, action });
      message.success(
        action === 'approve' ? t('config.changeStatus.approved') : t('config.changeStatus.rejected')
      );
      refetchChanges();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
    }
  };

  const backupColumns = [
    {
      title: tCommon('field.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: tCommon('field.type'),
      dataIndex: 'backup_type',
      key: 'backup_type',
      width: 100,
      render: (v: string) => {
        const info = BACKUP_TYPE_MAP[v];
        return info ? <Tag color={info.color}>{t(info.labelKey)}</Tag> : <Tag>{v}</Tag>;
      }
    },
    {
      title: t('config.column.fileSize'),
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (v: number | null) => (v ? `${(v / 1024).toFixed(1)} KB` : '-')
    },
    {
      title: t('config.column.configHash'),
      dataIndex: 'config_hash',
      key: 'config_hash',
      width: 120,
      render: (v: string) => (v ? v.slice(0, 12) + '...' : '-'),
      ellipsis: true
    },
    {
      title: tCommon('field.actions'),
      key: 'action',
      width: 140,
      render: (_: unknown, r: DeviceConfigBackup) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(r)}>
            {tCommon('action.view')}
          </Button>
          <Button type="link" size="small" icon={<SwapOutlined />} onClick={() => handleDiff(r)}>
            {t('config.action.diff')}
          </Button>
        </Space>
      )
    }
  ];

  const changeColumns = [
    {
      title: tCommon('field.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: t('config.column.summary'),
      dataIndex: 'change_summary',
      key: 'change_summary',
      render: (v: string) => v || '-',
      ellipsis: true
    },
    {
      title: tCommon('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => {
        const info = CHANGE_STATUS_MAP[v];
        return info ? <Tag color={info.color}>{t(info.labelKey)}</Tag> : <Tag>{v}</Tag>;
      }
    },
    {
      title: tCommon('field.actions'),
      key: 'action',
      width: 140,
      render: (_: unknown, r: DeviceConfigChange) => (
        <Space>
          {r.status === 'pending' && (
            <>
              <Button
                type="link"
                size="small"
                icon={<CheckOutlined />}
                style={{ color: '#52c41a' }}
                onClick={() =>
                  confirm({
                    title: t('config.confirmApprove'),
                    onOk: () => handleApprove(r, 'approve')
                  })
                }
              >
                {t('config.action.approve')}
              </Button>
              <Button
                type="link"
                size="small"
                danger
                icon={<CloseOutlined />}
                onClick={() =>
                  confirm({
                    title: t('config.confirmReject'),
                    okButtonProps: { danger: true },
                    onOk: () => handleApprove(r, 'reject')
                  })
                }
              >
                {t('config.action.reject')}
              </Button>
            </>
          )}
          {r.status === 'approved' && (
            <Tag color="green">{t('config.changeStatus.approved')}</Tag>
          )}
          {r.status === 'rejected' && <Tag color="red">{t('config.changeStatus.rejected')}</Tag>}
          {r.status === 'applied' && <Tag color="blue">{t('config.changeStatus.applied')}</Tag>}
          {r.status === 'draft' && <Tag>{t('config.changeStatus.draft')}</Tag>}
        </Space>
      )
    }
  ];

  const tabItems = [
    {
      key: 'backups',
      label: t('config.tab.backups'),
      children: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleBackup}
              loading={backupConfig.isPending}
            >
              {t('config.action.triggerBackup')}
            </Button>
          </div>
          <DataTable<DeviceConfigBackup>
            columns={backupColumns}
            dataSource={backups ?? []}
            loading={loadingBackups}
            rowKey="id"
            size="small"
            showCard={false}
            searchable={false}
            pagination={DENSE_PAGINATION}
          />
        </div>
      )
    },
    {
      key: 'changes',
      label: t('config.tab.changes'),
      children: (
        <DataTable<DeviceConfigChange>
          columns={changeColumns}
          dataSource={changes ?? []}
          loading={loadingChanges}
          rowKey="id"
          size="small"
          showCard={false}
          searchable={false}
          pagination={DENSE_PAGINATION}
        />
      )
    }
  ];

  return (
    <div>
      <Tabs items={tabItems} />

      {/* 查看配置内容弹窗 */}
      <Modal
        title={t('config.viewTitle')}
        open={viewContent !== null}
        onCancel={() => setViewContent(null)}
        footer={null}
        width={720}
      >
        <pre
          style={{
            maxHeight: 500,
            overflow: 'auto',
            fontSize: 12,
            background: '#f5f5f5',
            padding: 12,
            borderRadius: 4
          }}
        >
          {viewContent}
        </pre>
      </Modal>

      {/* 配置对比弹窗 */}
      <Modal
        title={t('config.diffTitle')}
        open={diffContent !== null}
        onCancel={() => setDiffContent(null)}
        footer={null}
        width={900}
      >
        {diffContent && (
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <h4 style={{ marginBottom: 8 }}>{t('config.oldConfig')}</h4>
              <pre
                style={{
                  maxHeight: 500,
                  overflow: 'auto',
                  fontSize: 12,
                  background: '#fff1f0',
                  padding: 12,
                  borderRadius: 4
                }}
              >
                {diffContent.old}
              </pre>
            </div>
            <div style={{ flex: 1 }}>
              <h4 style={{ marginBottom: 8 }}>{t('config.newConfig')}</h4>
              <pre
                style={{
                  maxHeight: 500,
                  overflow: 'auto',
                  fontSize: 12,
                  background: '#f6ffed',
                  padding: 12,
                  borderRadius: 4
                }}
              >
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
