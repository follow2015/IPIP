/**
 * PortBatchAddModal — 新增端口弹窗（批量多组 + 单条）
 * 自包含：内部持有 forms / 模式 / 预览 / 提交 mutation
 */
import { useMemo, useState } from 'react';
import { theme, Modal, Button, Form, Input, InputNumber, Select, Tag, Space, Row, Col } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useCreateNetworkPort, useBatchCreateNetworkPorts } from '@/services/network-port';
import { useMessage } from '@/hooks/useMessage';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import { expandPortGroups, previewPortNames } from './portNameBuilder';
import { getUsageStatusFormOptions } from './constants';
import { firstFieldError, isValidationError } from '@/utils/formError';

interface PortBatchAddModalProps {
  deviceId: number;
  open: boolean;
  onClose: () => void;
}

export function PortBatchAddModal({ deviceId, open, onClose }: PortBatchAddModalProps) {
  const { token } = theme.useToken();
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const [addMode, setAddMode] = useState<'batch' | 'single'>('batch');
  const [addForm] = Form.useForm();
  const [batchForm] = Form.useForm();
  const createPort = useCreateNetworkPort(deviceId);
  const batchCreatePort = useBatchCreateNetworkPorts(deviceId);

  const batchGroups = Form.useWatch('groups', batchForm);
  const batchPreview = useMemo(() => previewPortNames(batchGroups), [batchGroups]);
  const usageStatusOptions = getUsageStatusFormOptions(t);

  const resetAndClose = () => {
    onClose();
    addForm.resetFields();
    batchForm.resetFields();
  };

  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createPort.mutateAsync(values);
      message.success(t('port.message.createSuccess'));
      resetAndClose();
    } catch (err) {
      if (isValidationError(err)) {
        const fieldError = firstFieldError(err);
        if (fieldError) message.error(fieldError);
      } else {
        if (err instanceof Error) message.error(err.message);
      }
    }
  };

  const handleBatchAdd = async () => {
    try {
      const values = await batchForm.validateFields();
      const allPorts = expandPortGroups(values.groups);
      if (allPorts.length === 0) {
        message.error(t('port.message.noPortsToCreate'));
        return;
      }
      const result = await batchCreatePort.mutateAsync(allPorts);
      const created = result.data?.created_count ?? allPorts.length;
      const skipped = allPorts.length - created;
      if (skipped > 0) {
        message.success(t('port.message.batchCreatedWithSkipped', { count: created, skipped }));
      } else {
        message.success(t('port.message.batchCreated', { count: created }));
      }
      resetAndClose();
    } catch (err) {
      if (isValidationError(err)) {
        const fieldError = firstFieldError(err);
        if (fieldError) message.error(fieldError);
      } else {
        if (err instanceof Error) message.error(err.message);
      }
    }
  };

  return (
    <Modal
      title={t('port.action.add')}
      open={open}
      onOk={addMode === 'batch' ? handleBatchAdd : handleAdd}
      onCancel={resetAndClose}
      width={addMode === 'batch' ? 640 : 520}
      destroyOnHidden
    >
      {/* 模式切换 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button
            type={addMode === 'batch' ? 'primary' : 'default'}
            size="small"
            onClick={() => setAddMode('batch')}
          >
            {t('port.mode.batch')}
          </Button>
          <Button
            type={addMode === 'single' ? 'primary' : 'default'}
            size="small"
            onClick={() => setAddMode('single')}
          >
            {t('port.mode.single')}
          </Button>
        </Space>
      </div>

      {/* 批量模式（多组） */}
      {addMode === 'batch' && (
        <Form form={batchForm} layout="vertical">
          <div
            style={{
              marginBottom: 12,
              padding: '8px 12px',
              background: token.colorFillQuaternary,
              borderRadius: 6,
              fontSize: 12,
              lineHeight: 2,
              color: token.colorTextSecondary
            }}
          >
            <div style={{ fontWeight: 500, color: token.colorText, marginBottom: 2 }}>
              {t('port.namingRule')}
            </div>
            <div>
              {t('port.namingExample', { prefix: 'GE', slot: 0, card: 0, start: 1, end: 48 })} →{' '}
              <Tag style={{ margin: 0, fontSize: 11 }}>GE0/0/1</Tag> ~{' '}
              <Tag style={{ margin: 0, fontSize: 11 }}>GE0/0/48</Tag>
            </div>
            <div>
              {t('port.namingExample', { prefix: '10GE', slot: 0, card: 0, start: 1, end: 4 })} →{' '}
              <Tag style={{ margin: 0, fontSize: 11 }}>10GE0/0/1</Tag> ~{' '}
              <Tag style={{ margin: 0, fontSize: 11 }}>10GE0/0/4</Tag>
            </div>
          </div>
          <Form.List
            name="groups"
            initialValue={[
              {
                template: 'GE',
                slot: 0,
                card: 0,
                start_port: 1,
                end_port: 24,
                usage_status: 'free'
              }
            ]}
          >
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <div
                    key={key}
                    style={{
                      marginBottom: 12,
                      padding: '8px 12px',
                      border: `1px dashed ${token.colorBorder}`,
                      borderRadius: 6
                    }}
                  >
                    <Row gutter={8}>
                      <Col xs={24} md={8}>
                        <Form.Item
                          {...restField}
                          name={[name, 'template']}
                          label={t('nic.column.portType')}
                          initialValue="GE"
                          style={{ marginBottom: 8 }}
                        >
                          <Select
                            options={PORT_TYPE_TEMPLATES}
                            placeholder={t('form.portGeneration.template.placeholder')}
                            size="small"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={4}>
                        <Form.Item
                          {...restField}
                          name={[name, 'slot']}
                          label={t('form.portGeneration.slot.label')}
                          initialValue={0}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={4}>
                        <Form.Item
                          {...restField}
                          name={[name, 'card']}
                          label={t('form.portGeneration.card.label')}
                          initialValue={0}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={3}>
                        <Form.Item
                          {...restField}
                          name={[name, 'start_port']}
                          label={t('form.portGeneration.start.label')}
                          initialValue={1}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col xs={12} md={3}>
                        <Form.Item
                          {...restField}
                          name={[name, 'end_port']}
                          label={t('form.portGeneration.end.label')}
                          initialValue={24}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col xs={4} md={2} style={{ textAlign: 'right', paddingTop: 24 }}>
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
                  </div>
                ))}
                <Button
                  type="dashed"
                  onClick={() =>
                    add({
                      template: 'GE',
                      slot: 0,
                      card: 0,
                      start_port: 1,
                      end_port: 24,
                      usage_status: 'free'
                    })
                  }
                  icon={<PlusOutlined />}
                  size="small"
                  style={{ marginBottom: 8 }}
                >
                  {t('form.portGeneration.addGroup')}
                </Button>
              </>
            )}
          </Form.List>
          {/* 预览 */}
          {batchPreview.length > 0 && (
            <div
              style={{
                marginTop: 8,
                padding: '8px 12px',
                background: token.colorFillTertiary,
                borderRadius: 6,
                maxHeight: 160,
                overflowY: 'auto'
              }}
            >
              {/* 底色已走 Token，字色必须同源：原本字色写死中灰，暗色下底色翻深后
                  中灰字压在深底上会糊（典型半硬编码），改由 Token 派生。
                  注意此处是 JSX children 区，只能用 {/* * /} 形式，
                  写成 // 会被当字面文本渲染出来。 */}
              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 4 }}>
                {t('port.preview.count', { count: batchPreview.length })}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {batchPreview.map((name, idx) => (
                  <Tag key={`${name}_${idx}`} style={{ margin: 0, fontSize: 11 }}>
                    {name}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Form>
      )}

      {/* 单条模式 */}
      {addMode === 'single' && (
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="port_name"
            label={t('nic.column.portName')}
            rules={[{ required: true, message: t('port.validation.inputPortName') }]}
          >
            <Input placeholder={t('port.field.portNameHint')} />
          </Form.Item>
          <Form.Item name="port_type" label={t('nic.column.portType')}>
            <Input placeholder={t('port.field.portTypeHint')} />
          </Form.Item>
          <Form.Item name="speed" label={t('nic.column.speed')}>
            <Input placeholder={t('port.field.speedHint')} />
          </Form.Item>
          <Form.Item name="usage_status" label={t('port.column.usageStatus')} initialValue="free">
            <Select options={usageStatusOptions} />
          </Form.Item>
          <Form.Item name="description" label={tCommon('field.description')}>
            <Input placeholder={t('port.field.descriptionHint')} />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
