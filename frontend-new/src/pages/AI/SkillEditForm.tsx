import { Form, Input, InputNumber, Select, Switch, Button, Space, Card } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import type { SkillWritePayload } from '@/services/ai';

interface Props {
  initial?: SkillWritePayload;
  onSubmit: (payload: SkillWritePayload) => Promise<void>;
  onCancel: () => void;
  submitting?: boolean;
}

const STEP_TYPES = ['capability', 'llm', 'route'] as const;
const PARAM_TYPES = ['string', 'int', 'number', 'bool', 'array', 'object'];

const normalizeJson = (v: string): string | undefined => (v && v.trim() ? v : undefined);

const safeJsonParse = (v: unknown): unknown => {
  if (v === undefined || v === null || v === '') return undefined;
  if (typeof v !== 'string') return v;
  try {
    return JSON.parse(v);
  } catch {
    return undefined;
  }
};

export default function SkillEditForm({ initial, onSubmit, onCancel, submitting }: Props) {
  const [form] = Form.useForm<SkillWritePayload>();

  const handleFinish = async (values: SkillWritePayload) => {
    const payload: SkillWritePayload = {
      ...values,
      steps: (values.steps ?? []).map((step) => ({
        ...step,
        args: safeJsonParse(step.args) as Record<string, unknown> | undefined,
        branches: safeJsonParse(step.branches) as Record<string, string> | undefined
      })),
      return: safeJsonParse(values.return)
    };
    await onSubmit(payload);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={
        initial ?? {
          category: 'general',
          version: 1,
          max_llm_steps: 3,
          params: [],
          triggers: [],
          steps: []
        }
      }
      onFinish={handleFinish}
    >
      <Form.Item
        name="name"
        label="标识"
        rules={[
          { required: true, message: '必填' },
          {
            pattern: /^[a-z0-9][a-z0-9_-]{0,63}$/,
            message: '小写字母/数字/下划线/连字符，1-64 字符'
          }
        ]}
      >
        <Input disabled={!!initial} placeholder="my_skill" />
      </Form.Item>
      <Form.Item name="title" label="展示名">
        <Input />
      </Form.Item>
      <Form.Item name="description" label="描述" rules={[{ required: true }]}>
        <Input.TextArea rows={2} />
      </Form.Item>
      <Form.Item name="category" label="分类">
        <Input placeholder="general" />
      </Form.Item>
      <Form.Item name="version" label="版本">
        <InputNumber min={1} max={100} />
      </Form.Item>
      <Form.Item name="max_llm_steps" label="LLM 步骤上限">
        <InputNumber min={1} max={20} />
      </Form.Item>

      {/* params 动态列表 */}
      <Card size="small" title="参数声明">
        <Form.List name="params">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Space key={field.key} align="baseline" wrap>
                  <Form.Item
                    name={[field.name, 'name']}
                    rules={[{ required: true, message: '必填' }]}
                  >
                    <Input placeholder="参数名" />
                  </Form.Item>
                  <Form.Item name={[field.name, 'type']}>
                    <Select
                      options={PARAM_TYPES.map((t) => ({ label: t, value: t }))}
                      style={{ width: 100 }}
                    />
                  </Form.Item>
                  <Form.Item name={[field.name, 'required']} valuePropName="checked">
                    <Switch checkedChildren="必填" unCheckedChildren="可选" />
                  </Form.Item>
                  <Form.Item name={[field.name, 'description']}>
                    <Input placeholder="说明" />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(field.name)} />
                </Space>
              ))}
              <Button icon={<PlusOutlined />} onClick={() => add({})}>
                添加参数
              </Button>
            </>
          )}
        </Form.List>
      </Card>

      {/* steps 动态列表（B1 修复：必须完整渲染，否则编辑提交会清空 steps） */}
      <Card size="small" title="执行步骤">
        <Form.List name="steps">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Card key={field.key} size="small" type="inner" style={{ marginBottom: 8 }}>
                  <Space align="baseline" wrap>
                    <Form.Item
                      name={[field.name, 'id']}
                      rules={[{ required: true, message: '必填' }]}
                    >
                      <Input placeholder="步骤 id" />
                    </Form.Item>
                    <Form.Item name={[field.name, 'type']}>
                      <Select
                        options={STEP_TYPES.map((t) => ({ label: t, value: t }))}
                        style={{ width: 120 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'call']}
                      rules={[{ required: true, message: '必填' }]}
                    >
                      <Input placeholder="capability/prompt 名" />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                  <Form.Item name={[field.name, 'output']} label="输出别名">
                    <Input placeholder="result" />
                  </Form.Item>
                  <Form.Item name={[field.name, 'when']} label="条件（可选）">
                    <Input placeholder="true/false 表达式" />
                  </Form.Item>
                  <Form.Item name={[field.name, 'max_tokens']} label="max_tokens">
                    <InputNumber min={100} max={4096} />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, 'args']}
                    label="args（JSON）"
                    getValueFromEvent={normalizeJson}
                    rules={[
                      {
                        validator: (_, v) =>
                          v ? JSON.parse(v) && Promise.resolve() : Promise.resolve()
                      }
                    ]}
                  >
                    <Input.TextArea rows={2} placeholder='{"key": "{{ params.x }}"}' />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, 'branches']}
                    label="branches（JSON，route 专用）"
                    getValueFromEvent={normalizeJson}
                    rules={[
                      {
                        validator: (_, v) =>
                          v ? JSON.parse(v) && Promise.resolve() : Promise.resolve()
                      }
                    ]}
                  >
                    <Input.TextArea rows={2} placeholder='{"branch_a": "step_id_a"}' />
                  </Form.Item>
                </Card>
              ))}
              <Button
                icon={<PlusOutlined />}
                onClick={() => add({ type: 'capability', max_tokens: 500 })}
              >
                添加步骤
              </Button>
            </>
          )}
        </Form.List>
      </Card>

      {/* triggers 标签输入（B1 修复：必须渲染，否则清空） */}
      <Form.Item name="triggers" label="触发词">
        <Select mode="tags" placeholder="输入触发词后回车" />
      </Form.Item>

      {/* return JSON 编辑器（B1 修复：必须渲染，否则清空） */}
      <Form.Item
        name="return"
        label="返回值（Jinja 表达式或 JSON）"
        getValueFromEvent={normalizeJson}
        rules={[
          {
            validator: (_, v) => (v ? JSON.parse(v) && Promise.resolve() : Promise.resolve())
          }
        ]}
      >
        <Input.TextArea rows={2} placeholder='"{{ steps.search.output }}"' />
      </Form.Item>

      <Space>
        <Button type="primary" htmlType="submit" loading={submitting}>
          保存
        </Button>
        <Button onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </Space>
    </Form>
  );
}
