import { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Form, Input, Select, Switch, Divider, Alert, Space, Radio } from 'antd';
import {
  useBatchToggleDeviceMonitor,
  useBindDeviceCredential,
  useMetricTemplateGroups,
  useBatchUpdateMetricTemplateGroup,
  useBatchUpdatePortSyncEnabled
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';
import { MONITOR_PROTOCOL_OPTIONS } from '@/types/enums';
import MonitorCredentialForm, {
  buildCredentialPayload,
  buildDefaultCredentialName
} from '@/components/MonitorCredentialForm';
import type { Device } from '@/types/models';
import { getDeviceSubtypeLabel } from '@/types/statusMeta';

interface BatchUpdateMonitorModalProps {
  open: boolean;
  devices: Device[];
  onClose: (refresh?: boolean) => void;
}

function BatchUpdateMonitorModal({ open, devices, onClose }: BatchUpdateMonitorModalProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const [form] = Form.useForm();
  const [protocol, setProtocol] = useState<string>('snmp');
  const batchToggle = useBatchToggleDeviceMonitor();
  const createAndLink = useBindDeviceCredential();
  const batchUpdateGroup = useBatchUpdateMetricTemplateGroup();
  const batchUpdatePortSync = useBatchUpdatePortSyncEnabled();
  const message = useMessage();

  const firstDevice = devices[0];
  const subtypeLabel = firstDevice?.device_subtype
    ? (getDeviceSubtypeLabel(firstDevice.device_subtype, t) ?? firstDevice.device_subtype)
    : (firstDevice?.device_type ?? '');

  const hasNetworkDevice = devices.some((d) => d.device_type === 'network');
  const nonNetworkCount = devices.filter((d) => d.device_type !== 'network').length;

  const watchMonitorEnabled = Form.useWatch('monitor_enabled', form);
  const watchConfigureCredential = Form.useWatch('configure_credential', form);
  const watchConfigureGroup = Form.useWatch('configure_group', form);
  const watchConfigurePortSync = Form.useWatch('configure_port_sync', form);

  const lastAutoNameRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) lastAutoNameRef.current = null;
  }, [open]);

  const applyDefaultName = useCallback(
    (protocolValue: string) => {
      const current = (form.getFieldValue('credential_name') as string | undefined) ?? '';
      const untouched =
        current === lastAutoNameRef.current || (lastAutoNameRef.current === null && current === '');
      if (!untouched) return;
      const next = buildDefaultCredentialName(protocolValue, devices);
      if (next === current) return; // 值未变则不写，避免无谓的表单重渲染
      lastAutoNameRef.current = next;
      form.setFieldValue('credential_name', next);
    },
    [form, devices]
  );

  useEffect(() => {
    if (watchConfigureCredential) applyDefaultName(protocol);
  }, [watchConfigureCredential, protocol, applyDefaultName]);

  const { data: groups, isLoading: groupsLoading } = useMetricTemplateGroups();
  const candidateGroups =
    groups
      ?.filter((g) => !firstDevice?.device_type || g.device_type === firstDevice.device_type)
      .filter((g) => !g.vendor || !firstDevice?.brand || g.vendor === firstDevice.brand) ?? [];

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const deviceIds = devices.map((d) => d.id);

    if (values.monitor_enabled !== undefined) {
      try {
        const result = await batchToggle.mutateAsync({
          deviceIds,
          enabled: values.monitor_enabled
        });
        message.success(
          t(
            values.monitor_enabled
              ? 'batchMonitor.message.toggleResult.enabled'
              : 'batchMonitor.message.toggleResult.paused',
            { updated: result.updated, skipped: result.skipped }
          )
        );
      } catch (err) {
        message.error(err instanceof Error ? err.message : t('batchMonitor.message.toggleFailed'));
        return;
      }
    }

    if (values.configure_credential && values.protocol) {
      const p = values.protocol as string;
      const payload = buildCredentialPayload(p, values);

      try {
        await createAndLink.mutateAsync({
          protocol: p,
          payload,
          name: (values.credential_name as string) || '',
          device_ids: deviceIds
        });
        message.success(
          t('batchMonitor.message.credentialConfigured', {
            count: deviceIds.length,
            protocol: p.toUpperCase()
          })
        );
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : t('batchMonitor.message.credentialFailed')
        );
        return;
      }
    }

    if (values.configure_group) {
      const groupId = values.metric_template_group_id ?? null;
      try {
        const result = await batchUpdateGroup.mutateAsync({
          deviceIds,
          metricTemplateGroupId: groupId
        });
        message.success(
          groupId
            ? t('batchMonitor.message.groupBound', { count: result.updated })
            : t('batchMonitor.message.groupCleared', { count: result.updated })
        );
      } catch (err) {
        message.error(err instanceof Error ? err.message : t('batchMonitor.message.groupFailed'));
        return;
      }
    }

    if (values.configure_port_sync) {
      const mode = (values.port_sync_mode as string) || 'global';
      const portSyncEnabled = mode === 'on' ? true : mode === 'off' ? false : null;
      try {
        const result = await batchUpdatePortSync.mutateAsync({
          deviceIds,
          portSyncEnabled
        });
        const parts: string[] = [
          t(
            mode === 'on'
              ? 'batchMonitor.message.portSyncDone.forceOn'
              : mode === 'off'
                ? 'batchMonitor.message.portSyncDone.forceOff'
                : 'batchMonitor.message.portSyncDone.follow',
            { count: result.updated }
          )
        ];
        if (result.with_credential > 0) {
          parts.push(t('batchMonitor.message.withCredential', { count: result.with_credential }));
        }
        if (result.without_credential > 0) {
          parts.push(
            t('batchMonitor.message.withoutCredential', { count: result.without_credential })
          );
        }
        if (result.non_network > 0) {
          parts.push(t('batchMonitor.message.skipNonNetwork', { count: result.non_network }));
        }
        if (result.without_credential > 0) {
          message.warning(parts.join(t('batchMonitor.separator')));
        } else {
          message.success(parts.join(t('batchMonitor.separator')));
        }
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : t('batchMonitor.message.portSyncFailed')
        );
        return;
      }
    }

    onClose(true);
    form.resetFields();
  };

  const handleCancel = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title={t('batchMonitor.title', { count: devices.length, subtype: subtypeLabel })}
      open={open}
      onOk={handleSubmit}
      onCancel={handleCancel}
      confirmLoading={
        batchToggle.isPending ||
        createAndLink.isPending ||
        batchUpdateGroup.isPending ||
        batchUpdatePortSync.isPending
      }
      width={640}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{
          monitor_enabled: true,
          configure_credential: false,
          configure_group: false,
          configure_port_sync: false,
          port_sync_mode: 'global',
          protocol: 'snmp',
          snmp_version: 'v2c'
        }}
      >
        {/* 监控开关 */}
        <Divider plain>{t('batchMonitor.monitorSwitch')}</Divider>
        <Form.Item
          name="monitor_enabled"
          label={t('batchMonitor.monitorStatus')}
          valuePropName="checked"
        >
          <Switch
            checkedChildren={tCommon('action.enable')}
            unCheckedChildren={t('batchMonitor.paused')}
          />
        </Form.Item>
        <Alert
          type={watchMonitorEnabled ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
          message={watchMonitorEnabled ? t('batchMonitor.enableHint') : t('batchMonitor.pauseHint')}
        />

        {/* 凭据配置 */}
        <Divider plain>{t('batchMonitor.credentialTitle')}</Divider>
        <Form.Item
          name="configure_credential"
          label={t('batchMonitor.configCredential')}
          valuePropName="checked"
        >
          <Switch
            checkedChildren={t('batchMonitor.config')}
            unCheckedChildren={t('batchMonitor.skip')}
          />
        </Form.Item>

        {watchConfigureCredential && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={t('batchMonitor.credentialHint')}
            />
            <Form.Item label={t('credential.protocol')} name="protocol">
              <Select
                options={MONITOR_PROTOCOL_OPTIONS}
                onChange={(v) => {
                  setProtocol(v);
                  form.setFieldValue('snmp_version', 'v2c');
                }}
              />
            </Form.Item>

            <Form.Item
              label={t('batchMonitor.credentialName')}
              name="credential_name"
              rules={[{ required: true, message: t('credential.namePlaceholder') }]}
            >
              <Input placeholder={t('credential.nameHint')} />
            </Form.Item>

            <MonitorCredentialForm protocol={protocol} mode="create" />
          </>
        )}

        {!watchConfigureCredential && (
          <Alert type="info" showIcon message={t('batchMonitor.skipCredentialHint')} />
        )}

        {/* 指标模板组 */}
        <Divider plain>{t('credential.templateGroupTitle')}</Divider>
        <Form.Item
          name="configure_group"
          label={t('batchMonitor.configGroup')}
          valuePropName="checked"
        >
          <Switch
            checkedChildren={t('batchMonitor.config')}
            unCheckedChildren={t('batchMonitor.skip')}
          />
        </Form.Item>

        {watchConfigureGroup && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={t('batchMonitor.groupHint')}
            />
            <Form.Item
              label={t('credential.templateGroupTitle')}
              name="metric_template_group_id"
              extra={t('batchMonitor.groupClearHint')}
            >
              <Select
                allowClear
                placeholder={t('credential.selectTemplateGroup')}
                loading={groupsLoading}
                options={candidateGroups.map((g) => ({
                  value: g.id,
                  label: g.name,
                  disabled: g.enabled === false
                }))}
                optionFilterProp="label"
                showSearch
                notFoundContent={
                  <Space direction="vertical" size={2} style={{ padding: 8 }}>
                    <span>
                      {t('credential.noMatchedGroup', {
                        type: firstDevice?.device_type ?? t('credential.currentType')
                      })}
                    </span>
                    <span style={{ fontSize: 12, color: '#999' }}>
                      {t('credential.createInMonitorCenter')}
                    </span>
                  </Space>
                }
              />
            </Form.Item>
          </>
        )}

        {/* 端口同步开关（仅网络设备显示） */}
        {hasNetworkDevice && (
          <>
            <Divider plain>{t('batchMonitor.portSyncTitle')}</Divider>
            <Form.Item
              name="configure_port_sync"
              label={t('batchMonitor.configPortSync')}
              valuePropName="checked"
            >
              <Switch
                checkedChildren={t('batchMonitor.config')}
                unCheckedChildren={t('batchMonitor.skip')}
              />
            </Form.Item>

            {watchConfigurePortSync && (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={
                    nonNetworkCount > 0
                      ? t('batchMonitor.portSyncHintWithSkip', { count: nonNetworkCount })
                      : t('batchMonitor.portSyncHint')
                  }
                />
                <Form.Item
                  label={t('batchMonitor.syncMode')}
                  name="port_sync_mode"
                  extra={t('batchMonitor.syncModeHint')}
                >
                  <Radio.Group
                    options={[
                      { label: t('batchMonitor.modeFollow'), value: 'global' },
                      { label: t('batchMonitor.modeForceOn'), value: 'on' },
                      { label: t('batchMonitor.modeForceOff'), value: 'off' }
                    ]}
                  />
                </Form.Item>
              </>
            )}

            {!watchConfigurePortSync && (
              <Alert type="info" showIcon message={t('batchMonitor.skipPortSyncHint')} />
            )}
          </>
        )}
      </Form>
    </Modal>
  );
}

export default BatchUpdateMonitorModal;
