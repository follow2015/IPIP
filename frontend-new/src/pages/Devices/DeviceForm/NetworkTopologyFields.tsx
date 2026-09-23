/**
 * NetworkTopologyFields — 网络设备"网络拓扑"表单区块
 *
 * 从原 DeviceForm.tsx 拆出。角色/网络层/端口数量 + 上行设备/对端互联端口/
 * 本机上行端口 + 核心交换机选择，为 DeviceForm 中 handleSubmit 的 N2N
 * 连接自动创建逻辑提供表单字段。
 */

import { useMemo } from 'react';
import { Card, Row, Col, Form, Select, InputNumber } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSwitchList } from '@/services/switch';
import { useNetworkPorts } from '@/services/network-port';
import type { Device, Switch, SwitchPort } from '@/types/models';

export default function NetworkTopologyFields({
  form,
  isEdit,
  editRecord
}: {
  form: ReturnType<typeof Form.useForm>[0];
  isEdit: boolean;
  editRecord: Device | null;
}) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const { data: switchPage } = useSwitchList({ page: 1, page_size: 500 });
  const switchOptions = useMemo(
    () =>
      (switchPage?.items ?? []).map((s: Switch) => ({
        label: s.name || s.ip_address,
        value: s.device_id
      })),
    [switchPage]
  );

  const currentDeviceId = editRecord?.id ?? 0;
  const { data: localPorts } = useNetworkPorts(currentDeviceId, {
    enabled: !!editRecord?.id && isEdit
  });
  const localPortOptions = useMemo(
    () => (localPorts ?? []).map((p: SwitchPort) => ({ label: p.port_name, value: p.id })),
    [localPorts]
  );

  const uplinkDeviceId = Form.useWatch(['switch_config', 'uplink_device_id'], form);
  const { data: uplinkDevicePorts } = useNetworkPorts(uplinkDeviceId, {
    enabled: !!uplinkDeviceId
  });
  const uplinkDevicePortOptions = useMemo(
    () => (uplinkDevicePorts ?? []).map((p: SwitchPort) => ({ label: p.port_name, value: p.id })),
    [uplinkDevicePorts]
  );

  return (
    <Card
      title={t('form.section.networkTopology')}
      size="small"
      style={{ marginBottom: 16 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item name={['switch_config', 'switch_role']} label={t('form.networkTopology.role.label')}>
            <Select
              placeholder={tCommon('message.selectRequired')}
              allowClear
              options={[
                { label: t('form.networkTopology.roleOption.core'), value: 0 },
                { label: t('form.networkTopology.roleOption.access'), value: 1 }
              ]}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name={['switch_config', 'layer']} label={t('form.networkTopology.layer.label')}>
            <Select
              placeholder={tCommon('message.selectRequired')}
              allowClear
              options={[
                { label: t('form.networkTopology.layerOption.l2'), value: 2 },
                { label: t('form.networkTopology.layerOption.l3'), value: 3 }
              ]}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'port_num']}
            label={t('form.networkTopology.portCount.label')}
          >
            <InputNumber
              placeholder={t('form.networkTopology.portCount.placeholder')}
              style={{ width: '100%' }}
              min={0}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'uplink_device_id']}
            label={t('form.networkTopology.uplinkDevice.label')}
          >
            <Select
              placeholder={t('form.networkTopology.uplinkDevice.placeholder')}
              allowClear
              showSearch
              optionFilterProp="label"
              options={switchOptions}
              onChange={() => {
                form.setFieldValue(['switch_config', 'peer_port_ids'], undefined);
              }}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'peer_port_ids']}
            label={t('form.networkTopology.peerPorts.label')}
          >
            <Select
              placeholder={
                uplinkDeviceId
                  ? t('form.networkTopology.peerPorts.placeholder')
                  : t('form.hint.selectUplinkDeviceFirst')
              }
              allowClear
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={uplinkDevicePortOptions}
              disabled={!uplinkDeviceId}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'uplink_port_ids']}
            label={t('form.networkTopology.uplinkPorts.label')}
          >
            <Select
              placeholder={
                currentDeviceId
                  ? t('form.networkTopology.uplinkPorts.placeholder')
                  : t('form.networkTopology.uplinkPorts.placeholderAfterSave')
              }
              allowClear
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={localPortOptions}
              disabled={!isEdit || !currentDeviceId}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'core_device_id']}
            label={t('form.networkTopology.coreDevice.label')}
          >
            <Select
              placeholder={t('form.networkTopology.coreDevice.placeholder')}
              allowClear
              showSearch
              optionFilterProp="label"
              options={switchOptions}
            />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );
}
