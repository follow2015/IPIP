/**
 * 设备详情 - 监控凭据标签页
 *
 * 负责「共享凭据」的关联管理（计划 CredentialTab）：
 * 1. 展示本机已关联凭据，可取消某协议关联；
 * 2. 从已有共享凭据下拉选择并关联本机；
 * 3. 新建共享凭据（复用共享结构化表单 MonitorCredentialForm）并关联本机；
 * 4. 编辑本机某协议凭据密文（P0-2 设备级，只影响本设备）。
 *
 * 约束：绝不渲染凭据明文；列表只展示 name/protocol/linked_count。
 */
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Select,
  Input,
  Button,
  Space,
  Empty,
  Tag,
  Modal,
  Form,
  Alert,
  Switch,
  Typography
} from 'antd';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';
import { useConfirm } from '@/utils/confirm';
import {
  useDeviceMonitorStatus,
  useMonitorCredentials,
  useCreateAndLinkCredential,
  useLinkExistingCredential,
  useUnlinkCredential,
  useUpdateCredentialPayload,
  useToggleDeviceMonitor,
  useMetricTemplateGroups,
  type MonitorCredentialListItem
} from '@/services/monitor';
import { useUpdateDevice } from '@/services/device';
import MonitorCredentialForm from '@/components/MonitorCredentialForm';
import { MONITOR_PROTOCOL_OPTIONS } from '@/types/enums';
import type { Device } from '@/types/models';

interface CredCandidate {
  id: number;
  name: string | null;
  protocol: string;
  linked_count: number;
}

export default function CredentialTab({ device }: { device: Device }) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const deviceId = device.id;
  const { data: status } = useDeviceMonitorStatus(deviceId);
  const { data: creds = [] } = useMonitorCredentials();
  const createLink = useCreateAndLinkCredential();
  const linkExisting = useLinkExistingCredential();
  const unlink = useUnlinkCredential();
  const message = useMessage();

  const [protocol, setProtocol] = useState<string>('snmp');
  const [selectedCredId, setSelectedCredId] = useState<number | undefined>(undefined);

  const edit = useDisclosure();
  const [editTarget, setEditTarget] = useState<{ protocol: string; credentialId: number } | null>(
    null
  );
  const [editForm] = Form.useForm();
  const updateDeviceCred = useUpdateCredentialPayload(deviceId, editTarget?.credentialId ?? 0);
  const toggleMonitor = useToggleDeviceMonitor();

  const updateDevice = useUpdateDevice();
  const { data: groups, isLoading: groupsLoading } = useMetricTemplateGroups();
  const [selectedGroupId, setSelectedGroupId] = useState<number | null | undefined>(undefined);

  const currentGroupId = device.metric_template_group_id ?? null;
  const effectiveGroupId = selectedGroupId === undefined ? currentGroupId : selectedGroupId;
  const candidateGroups =
    groups
      ?.filter((g) => !device.device_type || g.device_type === device.device_type)
      .filter((g) => !g.vendor || !device.brand || g.vendor === device.brand) ?? [];
  const currentGroupName = groups?.find((g) => g.id === currentGroupId)?.name ?? null;

  const configured = status?.configured_protocols ?? [];

  const linkedCredentialIds = new Set(
    (status?.credentials ?? []).map((c) => c.credential_id).filter((id): id is number => id != null)
  );

  const candidates: CredCandidate[] = (creds as MonitorCredentialListItem[]).filter(
    (c): c is CredCandidate => c.id != null && !!c.protocol && !linkedCredentialIds.has(c.id)
  );

  const handleLinkExisting = async () => {
    if (selectedCredId == null) {
      message.warning(t('credential.selectSharedFirst'));
      return;
    }
    if (configured.length > 0) {
      confirm({
        title: t('credential.replaceTitle'),
        content: t('credential.replaceContent', {
          protocols: configured.map((p) => p.toUpperCase()).join(t('credential.separator'))
        }),
        okType: 'danger',
        okText: t('credential.confirmReplace'),
        onOk: async () => {
          try {
            await linkExisting.mutateAsync({
              credentialId: selectedCredId,
              device_ids: [deviceId]
            });
            message.success(t('credential.message.linked'));
            setSelectedCredId(undefined);
          } catch (err) {
            message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
          }
        }
      });
      return;
    }
    try {
      await linkExisting.mutateAsync({ credentialId: selectedCredId, device_ids: [deviceId] });
      message.success(t('credential.message.linked'));
      setSelectedCredId(undefined);
    } catch (err) {
      message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
    }
  };

  const handleUnlink = async (p: string) => {
    try {
      await unlink.mutateAsync({ deviceId, protocol: p });
      message.success(t('credential.message.unlinked', { protocol: p }));
    } catch (err) {
      message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
    }
  };

  const handleToggleMonitorEnabled = async (enabled: boolean) => {
    try {
      await toggleMonitor.mutateAsync({ deviceId, enabled });
      message.success(
        enabled ? t('credential.message.monitorResumed') : t('credential.message.monitorPaused')
      );
    } catch (err) {
      message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
    }
  };

  const handleSaveGroup = async () => {
    const groupId = effectiveGroupId;
    const isClearing = groupId === null && currentGroupId !== null;
    const doSave = async () => {
      try {
        await updateDevice.mutateAsync({
          id: deviceId,
          metric_template_group_id: groupId
        });
        message.success(
          groupId === null ? t('credential.message.groupCleared') : t('credential.message.groupUpdated')
        );
        setSelectedGroupId(undefined);
      } catch (err) {
        message.error(err instanceof Error ? err.message : t('credential.message.saveFailed'));
      }
    };
    if (isClearing) {
      confirm({
        title: t('credential.clearGroupTitle'),
        content: t('credential.clearGroupContent'),
        okType: 'danger',
        okText: t('credential.confirmClear'),
        onOk: doSave
      });
      return;
    }
    await doSave();
  };

  const handleCreateAndLink = async (values: Record<string, unknown>) => {
    const p = (values.protocol as string) || protocol;
    const payload: Record<string, unknown> = {};
    if (p === 'snmp') {
      const ver = (values.snmp_version as string) || 'v2c';
      payload.version = ver;
      if (ver === 'v2c') {
        payload.community = values.community;
      } else {
        payload.username = values.username;
        payload.auth_key = values.auth_key;
        payload.priv_key = values.priv_key;
        payload.auth_protocol = values.auth_protocol || 'sha';
        payload.priv_protocol = values.priv_protocol || 'aes';
      }
    } else if (p === 'zabbix') {
      payload.api_url = values.api_url;
      payload.api_token = values.api_token;
      if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
      if (values.match_by) payload.match_by = values.match_by;
    } else {
      payload.username = values.username;
      payload.password = values.password;
      if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
    }
    try {
      await createLink.mutateAsync({
        protocol: p,
        payload,
        name: (values.name as string) || undefined,
        device_ids: [deviceId]
      });
      message.success(t('credential.message.createdAndLinked'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : tCommon('message.operationFailed'));
    }
  };

  const handleOpenEdit = (p: string, credentialId: number) => {
    setEditTarget({ protocol: p, credentialId });
    edit.open();
  };

  const editInitialValues = (() => {
    if (!editTarget) return { snmp_version: 'v2c' };
    const linked = (creds as MonitorCredentialListItem[]).find(
      (c) => c.id === editTarget.credentialId
    );
    const meta = linked?.payload_meta || {};
    const initial: Record<string, unknown> = {
      snmp_version: (meta.snmp_version as string) || 'v2c'
    };
    for (const k of [
      'username',
      'auth_protocol',
      'priv_protocol',
      'api_url',
      'verify_ssl',
      'match_by',
      'community'
    ]) {
      if (meta[k] !== undefined) initial[k] = meta[k];
    }
    return initial;
  })();

  const handleSubmitEdit = async () => {
    if (!editTarget) return;
    let values: Record<string, unknown>;
    try {
      values = await editForm.validateFields();
    } catch {
      return;
    }
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === undefined || v === null || v === '') continue; // 留空保持不变
      payload[k] = v;
    }
    try {
      await updateDeviceCred.mutateAsync({ payload, name: (values.name as string) || undefined });
      message.success(t('credential.message.updated'));
      edit.close();
      editForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('credential.message.updateFailed'));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 0. 设备级监控启停（P1-6，仅影响本设备） */}
      <Card title={t('credential.monitorSwitchTitle')}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space orientation="vertical" size={0}>
            <Typography.Text strong>{t('credential.monitorEnabled')}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('credential.monitorEnabledHint')}
            </Typography.Text>
          </Space>
          <Switch
            checked={status?.status?.monitor_enabled !== false}
            loading={toggleMonitor.isPending}
            onChange={(checked) => handleToggleMonitorEnabled(checked)}
          />
        </Space>
      </Card>

      {/* 0.5 指标模板组关联 */}
      <Card title={t('credential.templateGroupTitle')}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space align="center" size={8}>
            <Typography.Text type="secondary">{t('credential.currentBinding')}</Typography.Text>
            {currentGroupId === null ? (
              <Tag color="default">{t('credential.autoMatch')}</Tag>
            ) : (
              <Tag color="blue">{currentGroupName ?? `#${currentGroupId}`}</Tag>
            )}
          </Space>
          <Alert
            type="info"
            showIcon
            message={t('credential.templateGroupHint')}
          />
          <Space style={{ width: '100%' }}>
            <Select
              style={{ width: 360 }}
              allowClear
              showSearch
              optionFilterProp="label"
              loading={groupsLoading}
              placeholder={t('credential.selectTemplateGroup')}
              value={effectiveGroupId ?? undefined}
              onChange={(v) => setSelectedGroupId(v ?? null)}
              options={candidateGroups.map((g) => ({
                value: g.id,
                label: g.name,
                disabled: g.enabled === false
              }))}
              notFoundContent={
                <Space direction="vertical" size={2} style={{ padding: 8 }}>
                  <span>
                    {t('credential.noMatchedGroup', {
                      type: device.device_type ?? t('credential.currentType')
                    })}
                  </span>
                  <span style={{ fontSize: 12, color: '#999' }}>
                    {t('credential.createInMonitorCenter')}
                  </span>
                </Space>
              }
            />
            <Button
              type="primary"
              loading={updateDevice.isPending}
              disabled={selectedGroupId === undefined || selectedGroupId === currentGroupId}
              onClick={handleSaveGroup}
            >
              {tCommon('action.save')}
            </Button>
          </Space>
        </Space>
      </Card>

      {/* 1. 本机已关联凭据 */}
      <Card title={t('credential.linkedTitle')}>
        {configured.length === 0 ? (
          <Empty description={t('credential.notLinked')} />
        ) : (
          <Space orientation="vertical" style={{ width: '100%' }}>
            {configured.map((p) => {
              const credInfo = status?.credentials?.find((c) => c.protocol === p);
              const credId = credInfo?.credential_id;
              const credName = credInfo?.name;
              return (
                <Space key={p} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space size="small">
                    <Tag color="blue">{p.toUpperCase()}</Tag>
                    <Typography.Text>{credName || '-'}</Typography.Text>
                  </Space>
                  <Space size="small">
                    {credId != null && (
                      <Button size="small" onClick={() => handleOpenEdit(p, credId)}>
                        {t('credential.editSecret')}
                      </Button>
                    )}
                    <Button
                      danger
                      size="small"
                      loading={unlink.isPending}
                      onClick={() => handleUnlink(p)}
                    >
                      {t('credential.unlink')}
                    </Button>
                  </Space>
                </Space>
              );
            })}
          </Space>
        )}
      </Card>

      {/* 2. 关联已有共享凭据 */}
      <Card title={t('credential.linkExistingTitle')}>
        {configured.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('credential.protocolExclusive')}
            description={t('credential.protocolExclusiveDesc', {
              protocols: configured.map((p) => p.toUpperCase()).join(t('credential.separator'))
            })}
          />
        )}
        <Space>
          <Select
            style={{ width: 320 }}
            placeholder={candidates.length ? t('credential.selectShared') : t('credential.noAvailable')}
            value={selectedCredId}
            onChange={setSelectedCredId}
            disabled={candidates.length === 0}
            options={candidates.map((c) => ({
              value: c.id,
              label: t('credential.sharedOption', {
                protocol: c.protocol.toUpperCase(),
                name: c.name || c.protocol,
                count: c.linked_count
              })
            }))}
          />
          <Button
            type="primary"
            disabled={candidates.length === 0 || selectedCredId == null}
            loading={linkExisting.isPending}
            onClick={handleLinkExisting}
          >
            {t('credential.linkThisDevice')}
          </Button>
        </Space>
        {candidates.length === 0 && (
          <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.45)' }}>{t('credential.noAvailable')}</div>
        )}
      </Card>

      {/* 3. 新建共享凭据并关联本机（复用共享结构化表单） */}
      <Card title={t('credential.createAndLinkTitle')}>
        {configured.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('credential.protocolExclusive')}
            description={t('credential.protocolExclusiveDescCreate', {
              protocols: configured.map((p) => p.toUpperCase()).join(t('credential.separator'))
            })}
          />
        )}
        <NewCredentialForm
          protocol={protocol}
          setProtocol={setProtocol}
          submitting={createLink.isPending}
          onSubmit={handleCreateAndLink}
          configuredProtocols={configured}
        />
      </Card>

      {/* 4. 本机编辑密文弹窗（P0-2 设备级） */}
      <Modal
        title={t('credential.editSecretTitle', { protocol: editTarget?.protocol ?? '' })}
        open={edit.isOpen}
        onCancel={() => {
          edit.close();
          editForm.resetFields();
        }}
        onOk={handleSubmitEdit}
        confirmLoading={updateDeviceCred.isPending}
        width={520}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('credential.onlyThisDevice')}
          description={t('credential.onlyThisDeviceDesc')}
        />
        <Form form={editForm} layout="vertical" initialValues={editInitialValues}>
          <Form.Item
            label={t('credential.name')}
            name="name"
            rules={[{ required: true, message: t('credential.namePlaceholder') }]}
          >
            <Input placeholder={t('credential.nameHint')} />
          </Form.Item>
          {editTarget && (
            <MonitorCredentialForm protocol={editTarget.protocol} mode="edit" form={editForm} />
          )}
        </Form>
      </Modal>
    </div>
  );
}

function NewCredentialForm({
  protocol,
  setProtocol,
  submitting,
  onSubmit,
  configuredProtocols
}: {
  protocol: string;
  setProtocol: (v: string) => void;
  submitting: boolean;
  onSubmit: (values: Record<string, unknown>) => void;
  configuredProtocols: string[];
}) {
  const { t } = useTranslation('device');
  const confirm = useConfirm();
  const [form] = Form.useForm();

  const handleFinish = (values: Record<string, unknown>) => {
    const newProtocol = (values.protocol as string) || protocol;
    if (configuredProtocols.length > 0 && !configuredProtocols.includes(newProtocol)) {
      confirm({
        title: t('credential.replaceTitle'),
        content: t('credential.protocolExclusiveDescCreate', {
          protocols: configuredProtocols.map((p) => p.toUpperCase()).join(t('credential.separator'))
        }),
        okType: 'danger',
        okText: t('credential.confirmReplace'),
        onOk: () => onSubmit(values)
      });
    } else {
      onSubmit(values);
    }
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{ protocol: 'snmp', snmp_version: 'v2c' }}
      onFinish={handleFinish}
    >
      <Space>
        <Form.Item label={t('credential.protocol')} name="protocol" style={{ width: 160 }}>
          <Select
            options={MONITOR_PROTOCOL_OPTIONS}
            onChange={(v) => {
              setProtocol(v);
              form.setFieldValue('snmp_version', 'v2c');
            }}
          />
        </Form.Item>
        <Form.Item
          label={t('credential.name')}
          name="name"
          style={{ width: 240 }}
          rules={[{ required: true, message: t('credential.namePlaceholder') }]}
        >
          <Input placeholder={t('credential.nameHint')} />
        </Form.Item>
      </Space>
      <MonitorCredentialForm protocol={protocol} mode="create" form={form} />
      <Button type="primary" htmlType="submit" loading={submitting}>
        {t('credential.createAndLink')}
      </Button>
    </Form>
  );
}
