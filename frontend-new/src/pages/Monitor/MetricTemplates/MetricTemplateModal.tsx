/**
 * 指标模板新增/编辑表单 Modal
 *
 * 从 MetricTemplates/index.tsx 拆分（M27）：结构化阈值按 metric_type 动态渲染。
 */
import { Modal, Form, Input, Select, InputNumber, Switch, Row, Col, type FormInstance } from 'antd';
import { useMessage } from '@/hooks/useMessage';
import { useUpsertMetricTemplate, type MetricTemplateItem } from '@/services/monitor';
import {
  DEVICE_TYPE_OPTIONS,
  SOURCE_OPTIONS,
  METRIC_TYPE_OPTIONS,
  buildThreshold,
  parseThreshold,
  type MetricTemplateFormValues
} from './shared';

interface MetricTemplateModalProps {
  open: boolean;
  editingRecord: MetricTemplateItem | null;
  form: FormInstance<MetricTemplateFormValues>;
  onClose: () => void;
}

export default function MetricTemplateModal({
  open,
  editingRecord,
  form,
  onClose
}: MetricTemplateModalProps) {
  const upsert = useUpsertMetricTemplate();
  const message = useMessage();

  
  const handleSubmit = async (values: MetricTemplateFormValues) => {
    const threshold = buildThreshold(values);
    if (values.metric_type === 'event' && values.threshold_json) {
      try {
        JSON.parse(values.threshold_json);
      } catch {
        message.error('阈值 JSON 格式不合法，请检查');
        return;
      }
    }
    try {
      await upsert.mutateAsync({
        device_type: values.device_type,
        metric_key: values.metric_key,
        category: values.category || null,
        display_name: values.display_name || null,
        vendor: values.vendor || null,
        source: values.source,
        mib: values.mib || null,
        oid_symbol: values.oid_symbol || null,
        oid: values.oid || null,
        zabbix_item_key: values.zabbix_item_key || null,
        index_kind: values.index_kind || null,
        metric_type: values.metric_type,
        unit: values.unit || null,
        poll_interval: values.poll_interval || 60,
        threshold,
        severity_default: values.severity_default || null,
        enabled: values.enabled ?? true,
        description: values.description || null,
        runbook_url: values.runbook_url || null,
        runbook_title: values.runbook_title || null
      });
      message.success(editingRecord ? '指标模板已更新' : '指标模板已保存');
      onClose();
    } catch {
      message.error('保存失败，请检查输入');
    }
  };

  
  const currentMetricType = Form.useWatch('metric_type', form) ?? 'gauge';
  
  const currentSource = Form.useWatch('source', form) ?? 'snmp';

  return (
    <Modal
      title={editingRecord ? '编辑指标模板' : '新增指标模板'}
      open={open}
      onOk={() => form.submit()}
      onCancel={onClose}
      confirmLoading={upsert.isPending}
      width={640}
      destroyOnHidden
    >
      <Form
        form={form}
        onFinish={handleSubmit}
        layout="vertical"
        initialValues={{ source: 'snmp', metric_type: 'gauge', poll_interval: 60, enabled: true }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label="设备类型"
              name="device_type"
              rules={[{ required: true, message: '请选择设备类型' }]}
            >
              <Select options={DEVICE_TYPE_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="指标 Key"
              name="metric_key"
              rules={[{ required: true, message: '请输入指标 Key' }]}
              tooltip="与 OID 分类规则 category 对齐的技术标识"
            >
              <Input placeholder="如 if_status / temperature / disk_failure" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label="显示名称"
              name="display_name"
              tooltip="中文显示名，表格优先展示；为空时回退 metric_key"
            >
              <Input placeholder="如 端口状态 / 温度 / 硬盘故障" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="分类 category"
              name="category"
              tooltip="关联 OID 分类规则，MIB 扫描导入时自动填充"
            >
              <Input placeholder="如 if_status / temperature" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label="厂商 vendor"
              name="vendor"
              tooltip="厂家约束（如 Huawei / H3C / Dell），声明时仅匹配同厂商设备；留空=全适用"
            >
              <Input placeholder="如 Dell / Huawei（留空=全适用）" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item label="来源" name="source">
              <Select options={SOURCE_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="类型" name="metric_type">
              <Select options={METRIC_TYPE_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="采集频率(秒)" name="poll_interval">
              <InputNumber min={10} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="MIB" name="mib">
              <Input placeholder="如 IF-MIB" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="OID 符号" name="oid_symbol" tooltip="MIB 符号名，如 ifOperStatus">
              <Input placeholder="如 ifOperStatus / entPhySensorValue" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          label="数字 OID"
          name="oid"
          tooltip="完整数字 OID，与 oid_symbol 互补；MIB 扫描导入时承接"
        >
          <Input placeholder="如 1.3.6.1.2.1.2.2.1.7" />
        </Form.Item>
        {currentSource === 'zabbix' && (
          <Form.Item
            label="Zabbix Item Key"
            name="zabbix_item_key"
            rules={[{ required: true, message: 'source=zabbix 时 item key 必填' }]}
            tooltip="Zabbix item key，如 system.cpu.util / vm.memory.size[pavailable]"
          >
            <Input placeholder="如 system.cpu.util / vm.memory.size[pavailable]" />
          </Form.Item>
        )}
        <Form.Item label="索引维度" name="index_kind">
          <Input placeholder="如 ifIndex（端口）" />
        </Form.Item>

        {}
        {(currentMetricType === 'gauge' || currentMetricType === 'counter') && (
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="告警阈值 (warn)" name="warn" tooltip="达到该值触发告警">
                <InputNumber style={{ width: '100%' }} placeholder="如 60" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="严重阈值 (crit)" name="crit" tooltip="达到该值触发严重告警">
                <InputNumber style={{ width: '100%' }} placeholder="如 70" />
              </Form.Item>
            </Col>
          </Row>
        )}
        {currentMetricType === 'state' && (
          <Form.Item label="期望值 (expected)" name="expected" tooltip="实际值不等于该值时告警">
            <Input placeholder="如 up / 1" />
          </Form.Item>
        )}
        {currentMetricType === 'event' && (
          <Form.Item label="阈值 JSON" name="threshold_json" tooltip="事件类型阈值，自由 JSON 结构">
            <Input.TextArea placeholder={'{\n  "pattern": "error"\n}'} rows={3} />
          </Form.Item>
        )}

        <Form.Item
          label="默认告警级别"
          name="severity_default"
          tooltip="未配置阈值时回退使用的告警级别"
        >
          <Select
            allowClear
            options={[
              { label: '告警 (warn)', value: 'warn' },
              { label: '严重 (crit)', value: 'crit' }
            ]}
            placeholder="选择默认级别"
          />
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="单位" name="unit">
              <Input placeholder="如 Celsius / Mbps" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="启用" name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item label="说明" name="description">
          <Input.TextArea rows={2} placeholder="指标含义、采集对象说明等" />
        </Form.Item>
        <Row gutter={16}>
          <Col span={16}>
            <Form.Item
              label="处置预案 URL"
              name="runbook_url"
              tooltip="告警触发时在告警详情展示的处置文档链接（内部 wiki 等）"
            >
              <Input placeholder="如 https://wiki.internal/runbook/temp-high" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="预案标题" name="runbook_title">
              <Input placeholder="如 温度过高处置流程" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
