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
        <Col span={16}>
          <Form.Item
            name="device_name"
            label="设备名称"
            rules={[{ required: true, message: '请输入设备名称' }]}
          >
            <Input
              placeholder="请输入设备名称"
              addonAfter={
                !showNodeAssoc ? (
                  <Button
                    type="text"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={onGenerateName}
                    title="自动生成"
                  />
                ) : undefined
              }
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name="device_type"
            label="设备主类型"
            rules={[{ required: true, message: '请选择设备主类型' }]}
          >
            <Select placeholder="请选择" options={typeOptions} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="device_subtype" label="设备子类型">
            <Select placeholder="请选择" options={subtypeOptions} allowClear />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="status" label="状态">
            <Select placeholder="请选择" options={statusOptions} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="responsible_person" label="负责人">
            <Select
              placeholder="请选择负责人"
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
        <Col span={8}>
          <Form.Item name="brand" label="品牌">
            <Select
              options={vendorOptions}
              showSearch
              allowClear
              placeholder="选择品牌"
              filterOption={(input, option) =>
                (option?.label as string).toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="device_model" label="型号">
            <Input placeholder="型号" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="power" label="功耗(W)">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="功耗" />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item
            name="metric_template_group_id"
            label="指标模板组（监控数据展示规则）"
            extra={
              <Space direction="vertical" size={0}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  不选择时按「设备类型 + 厂商 + 协议」自动匹配模板组
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  选择后将优先展示该组包含的监控指标
                </Typography.Text>
              </Space>
            }
          >
            <Select
              placeholder="不选择 = 自动匹配"
              options={templateGroupOptions}
              loading={groupsLoading}
              allowClear
              showSearch
              optionFilterProp="label"
              notFoundContent={
                <Space direction="vertical" size={2} style={{ padding: 8 }}>
                  <span>没有匹配 {watchDeviceType || '当前类型'} 的指标模板组</span>
                  <span style={{ fontSize: 12, color: '#999' }}>
                    可在「监控中心 → 指标模板」中创建
                  </span>
                </Space>
              }
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="serial_number" label="序列号（抄写设备标签）">
            <Input placeholder="抄写设备上的序列号" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="hostname" label="主机名">
            <Input placeholder="主机名" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="customer_id" label="客户">
            <Select
              placeholder="请选择客户"
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
          <Divider plain>节点关联</Divider>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="room_id"
                label="所属机房"
                rules={[{ required: true, message: '请选择机房' }]}
              >
                <Select placeholder="请先选择机房" options={roomOptions} allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="parent_device_id"
                label="所属机箱"
                rules={[{ required: true, message: '节点必须选择所属机箱' }]}
              >
                <Select
                  placeholder={selectedRoomId ? '请选择机箱' : '请先选择机房'}
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
            <Col span={8}>
              <Form.Item
                name="node_position"
                label="节点位置"
                rules={[{ required: true, message: '请选择节点位置' }]}
              >
                <Select
                  placeholder={selectedChassisId ? '请选择位置' : '请先选择机箱'}
                  disabled={!selectedChassisId || availablePositions.length === 0}
                  options={availablePositions.map((pos) => ({
                    label: `节点 ${pos}`,
                    value: pos
                  }))}
                />
              </Form.Item>
            </Col>
            {selectedChassisId && availablePositions.length > 0 && (
              <Col span={16} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
                <span style={{ color: '#8c8c8c', fontSize: 12 }}>
                  空余位置：{availablePositions.length} 个（
                  {availablePositions.slice(0, 10).join(', ')}
                  {availablePositions.length > 10 ? '...' : ''}）
                </span>
              </Col>
            )}
            {selectedChassisId && availablePositions.length === 0 && (
              <Col span={16} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
                <Alert
                  type="warning"
                  title="该机箱无空余节点位置"
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
