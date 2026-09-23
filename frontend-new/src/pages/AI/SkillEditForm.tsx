import { Form, Input, InputNumber, Select, Switch, Button, Space, Card } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import type { SkillWritePayload } from '@/services/ai';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
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
        label={t('skills.field.identifier')}
        rules={[
          { required: true, message: tc('validation.required') },
          {
            pattern: /^[a-z0-9][a-z0-9_-]{0,63}$/,
            message: t('skills.form.namePattern')
          }
        ]}
      >
        <Input disabled={!!initial} placeholder="my_skill" />
      </Form.Item>
      <Form.Item name="title" label={t('skills.field.displayName')}>
        <Input />
      </Form.Item>
      <Form.Item
        name="description"
        label={tc('field.description')}
        rules={[{ required: true }]}
      >
        <Input.TextArea rows={2} />
      </Form.Item>
      <Form.Item name="category" label={t('skills.field.category')}>
        <Input placeholder="general" />
      </Form.Item>
      <Form.Item name="version" label={t('skills.field.version')}>
        <InputNumber min={1} max={100} />
      </Form.Item>
      <Form.Item name="max_llm_steps" label={t('skills.form.maxLlmSteps')}>
        <InputNumber min={1} max={20} />
      </Form.Item>

      {/* params 动态列表 */}
      <Card size="small" title={t('skills.form.paramSection')}>
        <Form.List name="params">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Space key={field.key} align="baseline" wrap>
                  <Form.Item
                    name={[field.name, 'name']}
                    rules={[{ required: true, message: tc('validation.required') }]}
                  >
                    <Input placeholder={t('skills.form.paramNamePlaceholder')} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'type']}>
                    <Select
                      options={PARAM_TYPES.map((t) => ({ label: t, value: t }))}
                      style={{ width: 100 }}
                    />
                  </Form.Item>
                  <Form.Item name={[field.name, 'required']} valuePropName="checked">
                    <Switch
                      checkedChildren={t('skills.form.requiredLabel')}
                      unCheckedChildren={t('skills.form.optionalLabel')}
                    />
                  </Form.Item>
                  <Form.Item name={[field.name, 'description']}>
                    <Input placeholder={t('skills.form.remarkPlaceholder')} />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(field.name)} />
                </Space>
              ))}
              <Button icon={<PlusOutlined />} onClick={() => add({})}>
                {t('skills.form.addParam')}
              </Button>
            </>
          )}
        </Form.List>
      </Card>

      {/* steps 动态列表（B1 修复：必须完整渲染，否则编辑提交会清空 steps） */}
      <Card size="small" title={t('skills.form.stepSection')}>
        <Form.List name="steps">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Card key={field.key} size="small" type="inner" style={{ marginBottom: 8 }}>
                  <Space align="baseline" wrap>
                    <Form.Item
                      name={[field.name, 'id']}
                      rules={[{ required: true, message: tc('validation.required') }]}
                    >
                      <Input placeholder={t('skills.form.stepIdPlaceholder')} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'type']}>
                      <Select
                        options={STEP_TYPES.map((t) => ({ label: t, value: t }))}
                        style={{ width: 120 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'call']}
                      rules={[{ required: true, message: tc('validation.required') }]}
                    >
                      <Input placeholder={t('skills.form.stepCallPlaceholder')} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                  <Form.Item name={[field.name, 'output']} label={t('skills.form.outputAlias')}>
                    <Input placeholder="result" />
                  </Form.Item>
                  <Form.Item name={[field.name, 'when']} label={t('skills.form.conditionOptional')}>
                    <Input placeholder={t('skills.form.conditionPlaceholder')} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'max_tokens']} label="max_tokens">
                    <InputNumber min={100} max={4096} />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, 'args']}
                    label={t('skills.form.args')}
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
                    label={t('skills.form.branches')}
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
                {t('skills.form.addStep')}
              </Button>
            </>
          )}
        </Form.List>
      </Card>

      {/* triggers 标签输入（B1 修复：必须渲染，否则清空） */}
      <Form.Item name="triggers" label={t('skills.field.triggers')}>
        <Select mode="tags" placeholder={t('skills.form.triggerPlaceholder')} />
      </Form.Item>

      {/* return JSON 编辑器（B1 修复：必须渲染，否则清空） */}
      <Form.Item
        name="return"
        label={t('skills.form.returnValue')}
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
          {tc('action.save')}
        </Button>
        <Button onClick={onCancel} disabled={submitting}>
          {tc('action.cancel')}
        </Button>
      </Space>
    </Form>
  );
}
