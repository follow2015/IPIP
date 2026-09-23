/**
 * 批量修改配置弹窗
 *
 * 与「批量修改资产信息」并列，但面向设备配置：
 *  - 通用字段（所有设备）：品牌 / 型号 / 功耗 / 负责人 / 客户
 *  - 服务器（非机箱）子类型：硬件配置（CPU/内存/显卡/硬盘/网卡 + IPMI 用户/密码，不含 IPMI 地址）+ 网卡端口生成
 *  - 网络设备子类型：网络拓扑（角色/网络层/上行设备/核心交换机）+ 端口生成（上行端口仅支持单台设备修改）
 *
 * 调用方须保证选中的设备子类型一致（本弹窗仅做兜底提示）。
 */
import { useMemo } from 'react';
import {
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Row,
  Col,
  Divider,
  Card,
  Alert,
  Button,
  Typography,
  Space
} from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useBatchUpdateDeviceConfig, type BatchUpdateConfigRequest } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useUserOptions } from '@/services/user';
import { useComponentTemplates } from '@/services/component-template';
import { useSwitchList } from '@/services/switch';
import { useVendorBrands } from '@/services/monitor';
import HardwareConfigFields, {
  buildStorageSummary,
  buildStorageList
} from '@/components/HardwareConfigFields';
import NicConfigFields, { expandNicPorts } from '@/components/NicConfigFields';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import type { Device, Switch } from '@/types/models';
import { DeviceType, DeviceSubtype } from '@/types/enums';
import { getDeviceSubtypeLabel } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface BatchUpdateConfigModalProps {
  open: boolean;
  devices: Device[];
  onClose: (refresh?: boolean) => void;
}

const HW_FIELDS = [
  'cpu_template_id',
  'cpu_way',
  'cpu_cores',
  'cpu',
  'memory_template_id',
  'memory_dimm_count',
  'memory_size_gb',
  'memory',
  'gpu_template_id',
  'gpu_count',
  'gpu',
  'os_version',
  'ipmi_username',
  'ipmi_password'
] as const;

function BatchUpdateConfigModal({ open, devices, onClose }: BatchUpdateConfigModalProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const [form] = Form.useForm();
  const batchUpdateConfig = useBatchUpdateDeviceConfig();
  const message = useMessage();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const { data: userOptions } = useUserOptions();
  const { data: vendorBrands } = useVendorBrands();
  const firstDevice = devices[0];
  const deviceType = firstDevice?.device_type;
  const deviceSubtype = firstDevice?.device_subtype as DeviceSubtype | null | undefined;
  const isServerHw = deviceType === DeviceType.SERVER && deviceSubtype !== DeviceSubtype.CHASSIS;
  const isNetwork = deviceType === DeviceType.NETWORK;
  const isManagedNetwork = isNetwork && !!firstDevice?.switch_credential?.has_ssh;
  const vendorOptions = (vendorBrands?.items ?? [])
    .filter((v) => v.enabled && (!deviceType || v.device_type === deviceType))
    .map((v) => ({ key: v.id, label: v.label, value: v.enterprise_no }));
  const isUnmanagedNetwork = isNetwork && !firstDevice?.switch_credential?.has_ssh;
  const subtypeLabel = deviceSubtype
    ? (getDeviceSubtypeLabel(deviceSubtype, t) ?? deviceSubtype)
    : (deviceType ?? '');

  const formCustomerId = Form.useWatch('customer_id', form);
  const customerId = (formCustomerId ?? firstDevice?.customer_id ?? null) as number | null;

  const { data: nicComponentTemplates = [] } = useComponentTemplates('nic', customerId);

  const { data: switchPage } = useSwitchList({ page: 1, page_size: 500 });
  const switchOptions = useMemo(
    () =>
      (switchPage?.items ?? []).map((s: Switch) => ({
        label: s.name || s.ip_address,
        value: s.device_id
      })),
    [switchPage]
  );

  const portGroups = Form.useWatch('port_groups', form);
  const portPreview = useMemo(() => {
    if (!portGroups || portGroups.length === 0) return [];
    const allPorts: string[] = [];
    for (const group of portGroups) {
      const { template, slot, card, start, end, custom_prefix } = group ?? {};
      if (!template || !start || !end || start > end) continue;
      const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
      const prefix = template === 'custom' ? (custom_prefix ?? '') : (tpl?.prefix ?? '');
      if (!prefix) continue;
      const s = slot ?? 0;
      const c = card ?? 0;
      for (let i = start; i <= end; i++) {
        allPorts.push(`${prefix}${s}/${c}/${i}`);
      }
    }
    return allPorts.slice(0, 500);
  }, [portGroups]);

  const handleSubmit = async () => {
    const values = (await form.validateFields()) as Record<string, any>;

    const main: Record<string, unknown> = {};
    if (values.brand) main.brand = values.brand;
    if (values.device_model) main.device_model = values.device_model;
    if (values.power !== undefined && values.power !== null && values.power !== '')
      main.power = Number(values.power);
    if (
      values.responsible_person !== undefined &&
      values.responsible_person !== null &&
      values.responsible_person !== ''
    ) {
      main.responsible_person = Number(values.responsible_person);
    }
    if (
      values.customer_id !== undefined &&
      values.customer_id !== null &&
      values.customer_id !== ''
    ) {
      main.customer_id = Number(values.customer_id);
    }

    const payload: BatchUpdateConfigRequest = {
      ids: devices.map((d) => d.id),
      main
    };

    if (isServerHw) {
      const hw: Record<string, unknown> = {};
      for (const f of HW_FIELDS) {
        const v = values[f];
        if (v !== undefined && v !== null && v !== '') hw[f] = v;
      }
      const storageItems = values.storage_items as
        | {
            count?: number;
            capacity?: string;
            storage_type?: string;
            interface_type?: string;
            template_id?: number;
          }[]
        | undefined;
      if (storageItems && storageItems.length > 0) {
        const list = buildStorageList(storageItems);
        if (list.length > 0) payload.storage_items = list;
        const summary = buildStorageSummary(storageItems);
        if (summary) hw.storage_summary = summary;
      }
      if (Object.keys(hw).length > 0) payload.hardware = hw;

      const nicVal = values.nic_ports as { template_id?: number }[] | undefined;
      if (nicVal && nicVal.length > 0) {
        const expanded = expandNicPorts(nicVal, nicComponentTemplates);
        if (expanded.length > 0)
          payload.nic_ports = expanded as unknown as Record<string, unknown>[];
      }
    }

    if (isUnmanagedNetwork) {
      const sc = values.switch_config as Record<string, unknown> | undefined;
      if (sc && Object.keys(sc).length > 0) payload.switch_config = sc;

      const groups = values.port_groups as
        | {
            template?: string;
            slot?: number;
            card?: number;
            start?: number;
            end?: number;
            custom_prefix?: string;
          }[]
        | undefined;
      if (groups && groups.length > 0) {
        const ports: Record<string, unknown>[] = [];
        for (const g of groups) {
          const { template, slot, card, start, end, custom_prefix } = g ?? {};
          if (!template || !start || !end || start > end) continue;
          const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
          const prefix = template === 'custom' ? (custom_prefix ?? '') : (tpl?.prefix ?? '');
          const speed = template === 'custom' ? '' : (tpl?.speed ?? '');
          const portType = template === 'custom' ? '' : (tpl?.value ?? '');
          if (!prefix) continue;
          const s = slot ?? 0;
          const c = card ?? 0;
          for (let i = start; i <= end; i++) {
            ports.push({
              port_name: `${prefix}${s}/${c}/${i}`,
              port_type: portType,
              speed,
              usage_status: 'free'
            });
          }
        }
        if (ports.length > 0) payload.switch_ports = ports;
      }
    }

    try {
      const result = await batchUpdateConfig.mutateAsync(payload);
      const parts = [
        t('batch.message.updateResult', {
          updated: result.data.updated,
          skipped: result.data.skipped
        })
      ];
      if (result.data.nic_created)
        parts.push(t('batchConfig.message.nicPortsCreated', { count: result.data.nic_created }));
      if (result.data.port_created)
        parts.push(
          t('batchConfig.message.switchPortsCreated', { count: result.data.port_created })
        );
      if (result.data.storage_created)
        parts.push(t('batchConfig.message.storageCreated', { count: result.data.storage_created }));
      message.success(parts.join(t('batchConfig.separator')));
      onClose(true);
      form.resetFields();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title={t('batchConfig.title', { count: devices.length, subtype: subtypeLabel })}
      open={open}
      onOk={handleSubmit}
      onCancel={handleCancel}
      confirmLoading={batchUpdateConfig.isPending}
      width={820}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" preserve={false}>
        {/* 通用字段 */}
        <Divider plain>{t('batchConfig.section.general')}</Divider>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item name="brand" label={t('basic.field.brand')}>
              <Select
                options={vendorOptions}
                showSearch
                allowClear
                placeholder={t('form.basicInfo.brand.placeholder')}
                filterOption={(input, option) =>
                  (option?.label as string).toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="device_model" label={t('basic.field.model')}>
              <Input placeholder={t('form.basicInfo.model.placeholder')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="power" label={t('form.basicInfo.power.label')}>
              <InputNumber
                min={0}
                style={{ width: '100%' }}
                placeholder={t('form.basicInfo.power.placeholder')}
              />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="responsible_person" label={t('basic.field.owner')}>
              <Select
                placeholder={t('form.basicInfo.owner.placeholder')}
                options={userOptions}
                allowClear
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="customer_id" label={tCommon('field.customer')}>
              <Select
                placeholder={t('form.basicInfo.customer.placeholder')}
                options={customerOptions}
                allowClear
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </Col>
        </Row>

        {/* 服务器硬件配置 + 网卡 */}
        {isServerHw && (
          <>
            <Divider plain>{t('batchConfig.section.hardware')}</Divider>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={t('batchConfig.alert.ipmiBatchHint')}
            />
            <HardwareConfigFields
              form={form}
              customerId={customerId}
              showIpmi
              showIpmiAddress={false}
            />
            <NicConfigFields form={form} customerId={customerId} />
          </>
        )}

        {/* 网管型网络设备：仅通用字段 */}
        {isManagedNetwork && (
          <Alert
            type="warning"
            showIcon
            message={t('batchConfig.alert.managedNetworkLimited')}
          />
        )}

        {/* 非网管型网络设备拓扑 + 端口生成 */}
        {isUnmanagedNetwork && (
          <>
            <Divider plain>{t('form.section.networkTopology')}</Divider>
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item
                  name={['switch_config', 'switch_role']}
                  label={t('form.networkTopology.role.label')}
                >
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
                <Form.Item
                  name={['switch_config', 'layer']}
                  label={t('form.networkTopology.layer.label')}
                >
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
                  />
                </Form.Item>
              </Col>
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
              <Col xs={24} md={8}>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginTop: 4, marginBottom: 0 }}
                  message={t('batchConfig.alert.uplinkPortPerDevice')}
                />
              </Col>
            </Row>

            {/* 端口生成（支持多组） */}
            <Card
              title={t('form.section.portGeneration')}
              size="small"
              style={{ marginBottom: 16 }}
              styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
            >
              <div
                style={{
                  marginBottom: 8,
                  padding: '6px 12px',
                  background: '#fafafa',
                  borderRadius: 6,
                  fontSize: 12,
                  lineHeight: 1.8,
                  color: '#595959'
                }}
              >
                {t('form.portGeneration.intro')}
              </div>
              <Form.List
                name="port_groups"
                initialValue={[{ template: 'GE', slot: 0, card: 0, start: 1, end: 24 }]}
              >
                {(fields, { add, remove }) => (
                  <>
                    {fields.map(({ key, name, ...restField }) => (
                      <Row
                        key={key}
                        gutter={8}
                        align="top"
                        style={{
                          marginBottom: 8,
                          padding: '8px 0',
                          borderBottom: '1px dashed #f0f0f0'
                        }}
                      >
                        <Col xs={12} md={6}>
                          <Form.Item
                            {...restField}
                            name={[name, 'template']}
                            label={t('form.portGeneration.template.label')}
                            initialValue="GE"
                            style={{ marginBottom: 0 }}
                          >
                            <Select
                              options={PORT_TYPE_TEMPLATES}
                              placeholder={t('form.portGeneration.template.placeholder')}
                              size="small"
                            />
                          </Form.Item>
                        </Col>
                        <Col xs={12} md={3}>
                          <Form.Item
                            {...restField}
                            name={[name, 'slot']}
                            label={t('form.portGeneration.slot.label')}
                            initialValue={0}
                            style={{ marginBottom: 0 }}
                          >
                            <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                          </Form.Item>
                        </Col>
                        <Col xs={12} md={3}>
                          <Form.Item
                            {...restField}
                            name={[name, 'card']}
                            label={t('form.portGeneration.card.label')}
                            initialValue={0}
                            style={{ marginBottom: 0 }}
                          >
                            <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                          </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                          <Form.Item
                            {...restField}
                            name={[name, 'start']}
                            label={t('form.portGeneration.start.label')}
                            initialValue={1}
                            style={{ marginBottom: 0 }}
                          >
                            <InputNumber
                              min={0}
                              max={9999}
                              style={{ width: '100%' }}
                              size="small"
                            />
                          </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                          <Form.Item
                            {...restField}
                            name={[name, 'end']}
                            label={t('form.portGeneration.end.label')}
                            initialValue={24}
                            style={{ marginBottom: 0 }}
                          >
                            <InputNumber
                              min={0}
                              max={9999}
                              style={{ width: '100%' }}
                              size="small"
                            />
                          </Form.Item>
                        </Col>
                        <Col xs={12} md={3} style={{ textAlign: 'right', paddingTop: 22 }}>
                          {fields.length > 1 && (
                            <Button
                              type="text"
                              danger
                              icon={<MinusCircleOutlined />}
                              onClick={() => remove(name)}
                              size="small"
                            />
                          )}
                        </Col>
                      </Row>
                    ))}
                    <Button
                      type="dashed"
                      onClick={() => add({ template: 'GE', slot: 0, card: 0, start: 1, end: 24 })}
                      icon={<PlusOutlined />}
                      size="small"
                      style={{ marginBottom: 8 }}
                    >
                      {t('form.portGeneration.addGroup')}
                    </Button>
                  </>
                )}
              </Form.List>
              {portPreview.length > 0 && (
                <Alert
                  type="info"
                  showIcon
                  message={t('form.portGeneration.preview', {
                    count: portPreview.length,
                    list: portPreview.slice(0, 5).join(', '),
                    ellipsis: portPreview.length > 5 ? ' ...' : ''
                  })}
                  style={{ marginBottom: 8 }}
                />
              )}
            </Card>
          </>
        )}

        {/* 机箱子类型：仅支持通用字段 */}
        {!isServerHw && !isNetwork && (
          <Alert
            type="warning"
            showIcon
            message={t('batchConfig.alert.chassisNotSupported')}
          />
        )}
      </Form>
    </Modal>
  );
}

export default BatchUpdateConfigModal;
