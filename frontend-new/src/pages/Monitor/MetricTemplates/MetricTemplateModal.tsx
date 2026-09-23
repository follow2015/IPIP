/**
 * 指标模板新增/编辑表单 Modal
 *
 * 从 MetricTemplates/index.tsx 拆分（M27）：结构化阈值按 metric_type 动态渲染。
 */
import { Modal, Form, Input, Select, InputNumber, Switch, Row, Col, type FormInstance } from 'antd';
import { useMessage } from '@/hooks/useMessage';
import { useUpsertMetricTemplate, type MetricTemplateItem } from '@/services/monitor';
import { useTranslation } from 'react-i18next';
import {
  SOURCE_OPTIONS,
  buildDeviceTypeOptions,
  buildMetricTypeOptions,
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
  const { t } = useTranslation('monitor');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');

  const deviceTypeOptions = buildDeviceTypeOptions(td);
  const metricTypeOptions = buildMetricTypeOptions(t);

  const handleSubmit = async (values: MetricTemplateFormValues) => {
    const threshold = buildThreshold(values);
    if (values.metric_type === 'event' && values.threshold_json) {
      try {
        JSON.parse(values.threshold_json);
      } catch {
        message.error(t('metricTemplate.message.invalidThresholdJson'));
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
      message.success(
        editingRecord
          ? t('metricTemplate.message.updated')
          : t('metricTemplate.message.saved')
      );
      onClose();
    } catch {
      message.error(t('metricTemplate.message.saveFailed'));
    }
  };

  const currentMetricType = Form.useWatch('metric_type', form) ?? 'gauge';
  const currentSource = Form.useWatch('source', form) ?? 'snmp';

  return (
    <Modal
      title={editingRecord ? t('metricTemplate.modal.editTitle') : t('metricTemplate.modal.createTitle')}
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
          <Col xs={24} md={12}>
            <Form.Item
              label={td('switch.batchField.deviceType')}
              name="device_type"
              rules={[{ required: true, message: td('switch.form.deviceTypeRequired') }]}
            >
              <Select options={deviceTypeOptions} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              label={t('metricTemplate.field.metricKey')}
              name="metric_key"
              rules={[{ required: true, message: t('metricTemplate.validation.metricKeyRequired') }]}
              tooltip={t('metricTemplate.tooltip.metricKey')}
            >
              <Input placeholder={t('metricTemplate.placeholder.metricKey')} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item
              label={t('metricTemplate.field.displayName')}
              name="display_name"
              tooltip={t('metricTemplate.tooltip.displayName')}
            >
              <Input placeholder={t('metricTemplate.placeholder.displayName')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              label={t('metricTemplate.field.categoryKey')}
              name="category"
              tooltip={t('metricTemplate.tooltip.category')}
            >
              <Input placeholder={t('metricTemplate.placeholder.category')} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item
              label={t('metricTemplate.field.vendorKey')}
              name="vendor"
              tooltip={t('metricTemplate.tooltip.vendor')}
            >
              <Input placeholder={t('metricTemplate.placeholder.vendor')} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label={tc('field.source')} name="source">
              <Select options={SOURCE_OPTIONS} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label={tc('field.type')} name="metric_type">
              <Select options={metricTypeOptions} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label={t('metricTemplate.field.pollInterval')} name="poll_interval">
              <InputNumber min={10} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label="MIB" name="mib">
              <Input placeholder={t('metricTemplate.placeholder.mib')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              label={t('metricTemplate.field.oidSymbol')}
              name="oid_symbol"
              tooltip={t('metricTemplate.tooltip.oidSymbol')}
            >
              <Input placeholder={t('metricTemplate.placeholder.oidSymbol')} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          label={t('metricTemplate.field.numericOid')}
          name="oid"
          tooltip={t('metricTemplate.tooltip.numericOid')}
        >
          <Input placeholder={t('metricTemplate.placeholder.numericOid')} />
        </Form.Item>
        {currentSource === 'zabbix' && (
          <Form.Item
            label="Zabbix Item Key"
            name="zabbix_item_key"
            rules={[{ required: true, message: t('metricTemplate.validation.zabbixItemKeyRequired') }]}
            tooltip={t('metricTemplate.tooltip.zabbixItemKey')}
          >
            <Input placeholder={t('metricTemplate.placeholder.zabbixItemKey')} />
          </Form.Item>
        )}
        <Form.Item label={t('metricTemplate.field.indexKind')} name="index_kind">
          <Input placeholder={t('metricTemplate.placeholder.indexKind')} />
        </Form.Item>

        {/* 结构化阈值：按 metric_type 动态渲染 */}
        {(currentMetricType === 'gauge' || currentMetricType === 'counter') && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                label={t('metricTemplate.field.warn')}
                name="warn"
                tooltip={t('metricTemplate.tooltip.warn')}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  placeholder={t('metricTemplate.placeholder.warn')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                label={t('metricTemplate.field.crit')}
                name="crit"
                tooltip={t('metricTemplate.tooltip.crit')}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  placeholder={t('metricTemplate.placeholder.crit')}
                />
              </Form.Item>
            </Col>
          </Row>
        )}
        {currentMetricType === 'state' && (
          <Form.Item
            label={t('metricTemplate.field.expected')}
            name="expected"
            tooltip={t('metricTemplate.tooltip.expected')}
          >
            <Input placeholder={t('metricTemplate.placeholder.expected')} />
          </Form.Item>
        )}
        {currentMetricType === 'event' && (
          <Form.Item
            label={t('metricTemplate.field.thresholdJson')}
            name="threshold_json"
            tooltip={t('metricTemplate.tooltip.thresholdJson')}
          >
            <Input.TextArea placeholder={'{\n  "pattern": "error"\n}'} rows={3} />
          </Form.Item>
        )}

        <Form.Item
          label={t('metricTemplate.field.severityDefault')}
          name="severity_default"
          tooltip={t('metricTemplate.tooltip.severityDefault')}
        >
          <Select
            allowClear
            options={[
              { label: t('metricTemplate.severity.warn'), value: 'warn' },
              { label: t('metricTemplate.severity.crit'), value: 'crit' }
            ]}
            placeholder={t('metricTemplate.placeholder.severityDefault')}
          />
        </Form.Item>

        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label={t('metricTemplate.field.unit')} name="unit">
              <Input placeholder={t('metricTemplate.placeholder.unit')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label={tc('action.enable')} name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item label={tc('field.description')} name="description">
          <Input.TextArea rows={2} placeholder={t('metricTemplate.placeholder.description')} />
        </Form.Item>
        <Row gutter={16}>
          <Col xs={24} md={16}>
            <Form.Item
              label={t('metricTemplate.field.runbookUrl')}
              name="runbook_url"
              tooltip={t('metricTemplate.tooltip.runbookUrl')}
            >
              <Input placeholder={t('metricTemplate.placeholder.runbookUrl')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label={t('metricTemplate.field.runbookTitle')} name="runbook_title">
              <Input placeholder={t('metricTemplate.placeholder.runbookTitle')} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
