/**
 * 批量修改监控弹窗
 *
 * 功能：
 *  1. 批量设置监控开关（启用/暂停探测）
 *  2. 批量配置监控凭据（选择协议 + 填写凭据，复用 MonitorCredentialForm）
 *  3. 批量设置指标模板组
 *  4. 批量设置端口同步开关（跟随全局 / 强制开 / 强制关）
 *
 * 调用方须保证选中的设备子类型一致（本弹窗仅做兜底提示）。
 */
import { useState } from 'react';
import { Modal, Form, Input, Select, Switch, Divider, Alert, Space, Radio } from 'antd';
import {
  useBatchToggleDeviceMonitor,
  useCreateAndLinkCredential,
  useMetricTemplateGroups,
  useBatchUpdateMetricTemplateGroup,
  useBatchUpdatePortSyncEnabled
} from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';
import { MONITOR_PROTOCOL_OPTIONS } from '@/types/enums';
import MonitorCredentialForm from '@/components/MonitorCredentialForm';
import type { Device } from '@/types/models';
import { DEVICE_SUBTYPE_LABELS } from '@/types/enums';

interface BatchUpdateMonitorModalProps {
  open: boolean;
  
  devices: Device[];
  onClose: (refresh?: boolean) => void;
}

function BatchUpdateMonitorModal({ open, devices, onClose }: BatchUpdateMonitorModalProps) {
  const [form] = Form.useForm();
  const [protocol, setProtocol] = useState<string>('snmp');
  const batchToggle = useBatchToggleDeviceMonitor();
  const createAndLink = useCreateAndLinkCredential();
  const batchUpdateGroup = useBatchUpdateMetricTemplateGroup();
  const batchUpdatePortSync = useBatchUpdatePortSyncEnabled();
  const message = useMessage();

  const firstDevice = devices[0];
  const subtypeLabel = firstDevice?.device_subtype
    ? (DEVICE_SUBTYPE_LABELS[firstDevice.device_subtype as keyof typeof DEVICE_SUBTYPE_LABELS] ??
      firstDevice.device_subtype)
    : (firstDevice?.device_type ?? '');

  
  const hasNetworkDevice = devices.some((d) => d.device_type === 'network');
  const nonNetworkCount = devices.filter((d) => d.device_type !== 'network').length;

  const watchMonitorEnabled = Form.useWatch('monitor_enabled', form);
  const watchConfigureCredential = Form.useWatch('configure_credential', form);
  const watchConfigureGroup = Form.useWatch('configure_group', form);
  const watchConfigurePortSync = Form.useWatch('configure_port_sync', form);

  
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
          `监控已${values.monitor_enabled ? '启用' : '暂停'}：更新 ${result.updated} 台，跳过 ${result.skipped} 台`
        );
      } catch (err) {
        message.error(err instanceof Error ? err.message : '批量监控启停失败');
        return;
      }
    }

    
    if (values.configure_credential && values.protocol) {
      const p = values.protocol as string;
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
      }

      try {
        await createAndLink.mutateAsync({
          protocol: p,
          payload,
          name: (values.credential_name as string) || undefined,
          device_ids: deviceIds
        });
        message.success(`已为 ${deviceIds.length} 台设备配置 ${p.toUpperCase()} 凭据`);
      } catch (err) {
        message.error(err instanceof Error ? err.message : '批量配置凭据失败');
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
            ? `已为 ${result.updated} 台设备绑定指标模板组`
            : `已清除 ${result.updated} 台设备的指标模板组关联`
        );
      } catch (err) {
        message.error(err instanceof Error ? err.message : '批量更新指标模板组失败');
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
        const modeLabel = mode === 'on' ? '强制开启' : mode === 'off' ? '强制关闭' : '跟随全局';
        
        const parts: string[] = [`已${modeLabel} ${result.updated} 台网络设备的端口同步开关`];
        if (result.with_credential > 0) {
          parts.push(`${result.with_credential} 台有监控凭据可立即生效`);
        }
        if (result.without_credential > 0) {
          parts.push(`${result.without_credential} 台需配置 SNMP/Zabbix 凭据后才能同步`);
        }
        if (result.non_network > 0) {
          parts.push(`跳过 ${result.non_network} 台非网络设备`);
        }
        if (result.without_credential > 0) {
          message.warning(parts.join('，'));
        } else {
          message.success(parts.join('，'));
        }
      } catch (err) {
        message.error(err instanceof Error ? err.message : '批量更新端口同步开关失败');
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
      title={`批量修改监控（${devices.length} 台 · ${subtypeLabel}）`}
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
        {}
        <Divider plain>监控开关</Divider>
        <Form.Item name="monitor_enabled" label="监控状态" valuePropName="checked">
          <Switch checkedChildren="启用" unCheckedChildren="暂停" />
        </Form.Item>
        <Alert
          type={watchMonitorEnabled ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
          message={
            watchMonitorEnabled
              ? '启用后，监控 Worker 将在下一轮探测中纳入这些设备'
              : '暂停后，这些设备将不会被监控 Worker 探测，直到重新启用'
          }
        />

        {}
        <Divider plain>监控凭据</Divider>
        <Form.Item name="configure_credential" label="配置凭据" valuePropName="checked">
          <Switch checkedChildren="配置" unCheckedChildren="跳过" />
        </Form.Item>

        {watchConfigureCredential && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="将为所有选中设备配置相同的监控凭据（共享凭据模式）"
            />
            <Form.Item label="协议" name="protocol">
              <Select
                options={MONITOR_PROTOCOL_OPTIONS}
                onChange={(v) => {
                  setProtocol(v);
                  form.setFieldValue('snmp_version', 'v2c');
                }}
              />
            </Form.Item>

            <Form.Item label="凭据名称（可选）" name="credential_name">
              <Input placeholder="如：机房A SNMP只读团体字" />
            </Form.Item>

            <MonitorCredentialForm protocol={protocol} mode="create" form={form} />
          </>
        )}

        {!watchConfigureCredential && (
          <Alert type="info" showIcon message="跳过凭据配置，仅修改监控开关状态" />
        )}

        {}
        <Divider plain>指标模板组</Divider>
        <Form.Item name="configure_group" label="配置指标模板组" valuePropName="checked">
          <Switch checkedChildren="配置" unCheckedChildren="跳过" />
        </Form.Item>

        {watchConfigureGroup && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="为所有选中设备绑定统一的指标模板组；不选择模板组则保持自动匹配规则"
            />
            <Form.Item
              label="指标模板组"
              name="metric_template_group_id"
              extra="留空清除已绑定关系（回到按设备类型 + 厂商 + 协议自动匹配）；未开启本开关则不做任何改动"
            >
              <Select
                allowClear
                placeholder="选择指标模板组（留空 = 解除绑定）"
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
                    <span>没有匹配 {firstDevice?.device_type ?? '当前类型'} 的指标模板组</span>
                    <span style={{ fontSize: 12, color: '#999' }}>
                      可在「监控中心 → 指标模板」中创建
                    </span>
                  </Space>
                }
              />
            </Form.Item>
          </>
        )}

        {}
        {hasNetworkDevice && (
          <>
            <Divider plain>端口同步开关</Divider>
            <Form.Item name="configure_port_sync" label="配置端口同步" valuePropName="checked">
              <Switch checkedChildren="配置" unCheckedChildren="跳过" />
            </Form.Item>

            {watchConfigurePortSync && (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={
                    nonNetworkCount > 0
                      ? `批量设置网络设备的端口自动同步开关（选中含 ${nonNetworkCount} 台非网络设备将自动跳过）。非网管设备走全量替换，网管设备仅更新端口状态。需先配置 SNMP 或 Zabbix 监控凭据后才能生效。`
                      : '批量设置网络设备的端口自动同步开关。非网管设备走全量替换，网管设备仅更新端口状态。需先配置 SNMP 或 Zabbix 监控凭据后才能生效。'
                  }
                />
                <Form.Item
                  label="同步模式"
                  name="port_sync_mode"
                  extra="跟随全局=使用运行配置中心的默认开关；强制开/关=覆盖全局设置，仅对这些设备生效"
                >
                  <Radio.Group
                    options={[
                      { label: '跟随全局', value: 'global' },
                      { label: '强制开启', value: 'on' },
                      { label: '强制关闭', value: 'off' }
                    ]}
                  />
                </Form.Item>
              </>
            )}

            {!watchConfigurePortSync && (
              <Alert type="info" showIcon message="跳过端口同步开关配置，保持各设备当前设置" />
            )}
          </>
        )}
      </Form>
    </Modal>
  );
}

export default BatchUpdateMonitorModal;
