import {
  Alert,
  Button,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Typography
} from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import type { SelectProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useVendorBrands, useMetricTemplateGroups } from '@/services/monitor';

interface BasicInfoFieldsProps {
  typeOptions: SelectProps['options'];
  subtypeOptions: SelectProps['options'];
  statusOptions: SelectProps['options'];
  userOptions: SelectProps['options'];
  customerOptions: SelectProps['options'];
  roomOptions: SelectProps['options'];
  chassisOptions: SelectProps['options'];
  availablePositions: number[];
  selectedRoomId?: number | string;
  selectedChassisId?: number | string;
  showNodeAssoc: boolean;
  onGenerateName: () => void;
}

export default function BasicInfoFields({
  typeOptions,
  subtypeOptions,
  statusOptions,
  userOptions,
  customerOptions,
  roomOptions,
  chassisOptions,
  availablePositions,
  selectedRoomId,
  selectedChassisId,
  showNodeAssoc,
  onGenerateName
}: BasicInfoFieldsProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const { data: vendorBrands } = useVendorBrands();
  const formInstance = Form.useFormInstance();
  const watchDeviceType = Form.useWatch('device_type', formInstance) ?? '';
  const watchBrand = Form.useWatch('brand', formInstance) as string | undefined;
  const vendorOptions: { key: string | number; label: string; value: string }[] = (
    vendorBrands?.items ?? []
  )
    .filter((v) => v.enabled && (!watchDeviceType || v.device_type === watchDeviceType))
    .map((v) => ({ key: v.id, label: v.label, value: v.enterprise_no }));
  if (watchBrand && !vendorOptions.some((o) => o.value === watchBrand)) {
    vendorOptions.push({ key: `__fallback__${watchBrand}`, label: watchBrand, value: watchBrand });
  }

  const { data: groups, isLoading: groupsLoading } = useMetricTemplateGroups();
  const templateGroupOptions = (groups ?? [])
    .filter((g) => !watchDeviceType || g.device_type === watchDeviceType)
    .filter((g) => !g.vendor || !watchBrand || g.vendor === watchBrand)
    .map((g) => ({ label: g.name, value: g.id, disabled: g.enabled === false }));

  return (
    <>
      {/* ── 设备基本信息 ── */}
      <Row gutter={16}>
        <Col xs={24} md={16}>
          <Form.Item
            name="device_name"
            label={t('field.name')}
            rules={[{ required: true, message: t('form.basicInfo.deviceName.placeholder') }]}
          >
            <Input
              placeholder={t('form.basicInfo.deviceName.placeholder')}
              addonAfter={
                !showNodeAssoc ? (
                  <Button
                    type="text"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={onGenerateName}
                    title={t('form.basicInfo.autoGenerateTitle')}
                  />
                ) : undefined
              }
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name="device_type"
            label={t('form.basicInfo.mainType.label')}
            rules={[{ required: true, message: t('form.basicInfo.mainType.required') }]}
          >
            <Select placeholder={tCommon('message.selectRequired')} options={typeOptions} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item name="device_subtype" label={t('basic.field.deviceSubtype')}>
            <Select placeholder={tCommon('message.selectRequired')} options={subtypeOptions} allowClear />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name="status" label={tCommon('field.status')}>
            <Select placeholder={tCommon('message.selectRequired')} options={statusOptions} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name="responsible_person" label={t('basic.field.owner')}>
            <Select
              placeholder={t('form.basicInfo.owner.placeholder')}
              options={userOptions}
              allowClear
              showSearch
              optionFilterProp="label"
              fieldNames={{ label: 'label', value: 'value' }}
            />
          </Form.Item>
        </Col>
      </Row>
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
          <Form.Item
            name="metric_template_group_id"
            label={t('form.basicInfo.metricTemplateGroup.label')}
            extra={
              <Space direction="vertical" size={0}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('form.basicInfo.metricTemplateGroup.autoMatchHint')}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('form.basicInfo.metricTemplateGroup.priorityHint')}
                </Typography.Text>
              </Space>
            }
          >
            <Select
              placeholder={t('form.basicInfo.metricTemplateGroup.placeholder')}
              options={templateGroupOptions}
              loading={groupsLoading}
              allowClear
              showSearch
              optionFilterProp="label"
              notFoundContent={
                <Space direction="vertical" size={2} style={{ padding: 8 }}>
                  <span>
                    {t('credential.noMatchedGroup', {
                      type: watchDeviceType || t('credential.currentType')
                    })}
                  </span>
                  <span style={{ fontSize: 12, color: '#999' }}>
                    {t('credential.createInMonitorCenter')}
                  </span>
                </Space>
              }
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item
            name="serial_number"
            label={t('form.basicInfo.serialNumber.label')}
          >
            <Input placeholder={t('form.basicInfo.serialNumber.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name="hostname" label={t('node.field.hostname')}>
            <Input placeholder={t('form.basicInfo.hostname.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
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

      {/* ── 节点关联区块（子节点特有） ── */}
      {showNodeAssoc && (
        <>
          <Divider plain>{t('form.section.nodeAssoc')}</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="room_id"
                label={t('basic.field.room')}
                rules={[{ required: true, message: t('form.select.room') }]}
              >
                <Select
                  placeholder={t('form.hint.selectRoomFirst')}
                  options={roomOptions}
                  allowClear
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="parent_device_id"
                label={t('form.nodeAssoc.chassis.label')}
                rules={[{ required: true, message: t('form.nodeAssoc.chassis.required') }]}
              >
                <Select
                  placeholder={
                    selectedRoomId
                      ? t('form.select.chassis')
                      : t('form.hint.selectRoomFirst')
                  }
                  options={chassisOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  disabled={!selectedRoomId}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                name="node_position"
                label={t('node.field.position')}
                rules={[{ required: true, message: t('form.nodeAssoc.position.required') }]}
              >
                <Select
                  placeholder={
                    selectedChassisId
                      ? t('form.select.position')
                      : t('form.hint.selectChassisFirst')
                  }
                  disabled={!selectedChassisId || availablePositions.length === 0}
                  options={availablePositions.map((pos) => ({
                    label: t('form.nodeAssoc.position.option', { position: pos }),
                    value: pos
                  }))}
                />
              </Form.Item>
            </Col>
            {selectedChassisId && availablePositions.length > 0 && (
              <Col
                xs={24}
                md={16}
                style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}
              >
                <span style={{ color: '#8c8c8c', fontSize: 12 }}>
                  {t('form.nodeAssoc.vacantPositions', {
                    count: availablePositions.length,
                    list: availablePositions.slice(0, 10).join(', '),
                    ellipsis: availablePositions.length > 10 ? '...' : ''
                  })}
                </span>
              </Col>
            )}
            {selectedChassisId && availablePositions.length === 0 && (
              <Col
                xs={24}
                md={16}
                style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}
              >
                <Alert
                  type="warning"
                  title={t('form.nodeAssoc.noVacantPosition')}
                  style={{ padding: '2px 8px' }}
                  showIcon
                />
              </Col>
            )}
          </Row>
        </>
      )}
    </>
  );
}
