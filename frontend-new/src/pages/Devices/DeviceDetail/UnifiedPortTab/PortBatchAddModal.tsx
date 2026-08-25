/**
 * PortBatchAddModal — 新增端口弹窗（批量多组 + 单条）
 * 自包含：内部持有 forms / 模式 / 预览 / 提交 mutation
 */
import { useMemo, useState } from 'react';
import { Modal, Button, Form, Input, InputNumber, Select, Tag, Space, Row, Col } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useCreateNetworkPort, useBatchCreateNetworkPorts } from '@/services/network-port';
import { useMessage } from '@/hooks/useMessage';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import { expandPortGroups, previewPortNames } from './portNameBuilder';
import { USAGE_STATUS_FORM_OPTIONS } from './constants';

interface PortBatchAddModalProps {
  deviceId: number;
  open: boolean;
  onClose: () => void;
}

export function PortBatchAddModal({ deviceId, open, onClose }: PortBatchAddModalProps) {
  const message = useMessage();
  const [addMode, setAddMode] = useState<'batch' | 'single'>('batch');
  const [addForm] = Form.useForm();
  const [batchForm] = Form.useForm();
  const createPort = useCreateNetworkPort(deviceId);
  const batchCreatePort = useBatchCreateNetworkPorts(deviceId);

  const batchGroups = Form.useWatch('groups', batchForm);
  const batchPreview = useMemo(() => previewPortNames(batchGroups), [batchGroups]);

  const resetAndClose = () => {
    onClose();
    addForm.resetFields();
    batchForm.resetFields();
  };

  
  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createPort.mutateAsync(values);
      message.success('端口创建成功');
      resetAndClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleBatchAdd = async () => {
    try {
      const values = await batchForm.validateFields();
      const allPorts = expandPortGroups(values.groups);
      if (allPorts.length === 0) {
        message.error('没有可创建的端口');
        return;
      }
      const result = await batchCreatePort.mutateAsync(allPorts);
      const created = result.data?.created_count ?? allPorts.length;
      const skipped = allPorts.length - created;
      if (skipped > 0) {
        message.success(`成功创建 ${created} 个端口，${skipped} 个已存在被跳过`);
      } else {
        message.success(`成功创建 ${created} 个端口`);
      }
      resetAndClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal
      title="新增端口"
      open={open}
      onOk={addMode === 'batch' ? handleBatchAdd : handleAdd}
      onCancel={resetAndClose}
      width={addMode === 'batch' ? 640 : 520}
      destroyOnHidden
    >
      {}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button
            type={addMode === 'batch' ? 'primary' : 'default'}
            size="small"
            onClick={() => setAddMode('batch')}
          >
            批量添加
          </Button>
          <Button
            type={addMode === 'single' ? 'primary' : 'default'}
            size="small"
            onClick={() => setAddMode('single')}
          >
            单条添加
          </Button>
        </Space>
      </div>

      {}
      {addMode === 'batch' && (
        <Form form={batchForm} layout="vertical">
          <div
            style={{
              marginBottom: 12,
              padding: '8px 12px',
              background: '#fafafa',
              borderRadius: 6,
              fontSize: 12,
              lineHeight: 2,
              color: '#595959'
            }}
          >
            <div style={{ fontWeight: 500, color: '#262626', marginBottom: 2 }}>
              命名规则：前缀 + 槽位/卡号/端口号（支持多组）
            </div>
            <div>
              GE + 槽0/卡0/1~48 → <Tag style={{ margin: 0, fontSize: 11 }}>GE0/0/1</Tag> ~{' '}
              <Tag style={{ margin: 0, fontSize: 11 }}>GE0/0/48</Tag>
            </div>
            <div>
              10GE + 槽0/卡0/1~4 → <Tag style={{ margin: 0, fontSize: 11 }}>10GE0/0/1</Tag> ~{' '}
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
                      border: '1px dashed #d9d9d9',
                      borderRadius: 6
                    }}
                  >
                    <Row gutter={8}>
                      <Col span={8}>
                        <Form.Item
                          {...restField}
                          name={[name, 'template']}
                          label="端口类型"
                          initialValue="GE"
                          style={{ marginBottom: 8 }}
                        >
                          <Select
                            options={PORT_TYPE_TEMPLATES}
                            placeholder="选择类型"
                            size="small"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={4}>
                        <Form.Item
                          {...restField}
                          name={[name, 'slot']}
                          label="槽位"
                          initialValue={0}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col span={4}>
                        <Form.Item
                          {...restField}
                          name={[name, 'card']}
                          label="卡号"
                          initialValue={0}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          {...restField}
                          name={[name, 'start_port']}
                          label="起始"
                          initialValue={1}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          {...restField}
                          name={[name, 'end_port']}
                          label="结束"
                          initialValue={24}
                          style={{ marginBottom: 8 }}
                        >
                          <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                        </Form.Item>
                      </Col>
                      <Col span={2} style={{ textAlign: 'right', paddingTop: 24 }}>
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
                  添加端口组
                </Button>
              </>
            )}
          </Form.List>
          {}
          {batchPreview.length > 0 && (
            <div
              style={{
                marginTop: 8,
                padding: '8px 12px',
                background: '#f6f6f6',
                borderRadius: 6,
                maxHeight: 160,
                overflowY: 'auto'
              }}
            >
              <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>
                将创建 {batchPreview.length} 个端口：
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

      {}
      {addMode === 'single' && (
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="port_name"
            label="端口名称"
            rules={[{ required: true, message: '请输入端口名称' }]}
          >
            <Input placeholder="如 GE1/0/1" />
          </Form.Item>
          <Form.Item name="port_type" label="端口类型">
            <Input placeholder="如 GE" />
          </Form.Item>
          <Form.Item name="speed" label="速率">
            <Input placeholder="如 1G" />
          </Form.Item>
          <Form.Item name="usage_status" label="占用状态" initialValue="free">
            <Select options={USAGE_STATUS_FORM_OPTIONS} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="端口描述" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
