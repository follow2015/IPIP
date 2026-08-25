/**
 * SchemaForm — Schema 驱动表单组件
 *
 * 【展示组件】纯 Props 驱动，不内部获取数据，不直接订阅 Store。
 *
 * 加强点：
 * 1. 新增控件类型：password、InputNumber 支持 min/max/step
 * 2. 新增 Modal 包裹模式：传 modalProps 时自动包裹 Modal，省去外部手写
 * 3. 保留 formRef 暴露 Form 实例
 * 4. 保留 onSuccess/onCancel 回调
 *
 * 适用场景：纯 Input/Select/Number/TextArea/Password 的简单表单
 * 不适用：需要 Row/Col 布局、字段联动、动态显隐、自定义渲染的复杂表单（用 useCrudForm + 手写 JSX）
 */
import React from 'react';
import {
  Button,
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Switch,
  Radio,
  Space,
  Modal,
} from 'antd';
import type { FormInstance, Rule } from 'antd/es/form';

export interface FormFieldSchema {
  name:          string;
  label:         string;
  type:          'input' | 'password' | 'select' | 'number' | 'textarea' | 'date' | 'switch' | 'radio' | 'custom';
  required?:     boolean;
  rules?:        Rule[];
  options?:      { label: string; value: string | number }[];
  placeholder?:  string;
  defaultValue?: unknown;
  component?:    React.ComponentType;
  span?:         number;
  disabled?:     boolean;
  mode?:         'multiple' | undefined;
  min?: number;
  max?: number;
  step?: number;
  rows?: number;
}

export interface FormSchema {
  fields: FormFieldSchema[];
}

export interface SchemaFormProps {
  schema:          FormSchema;
  initialValues?:  Record<string, unknown>;
  onSubmit:        (values: Record<string, unknown>) => Promise<void>;
  onSuccess?:      () => void;
  onCancel?:       () => void;
  loading?:        boolean;
  layout?:         'horizontal' | 'vertical' | 'inline';
  formRef?:        React.Ref<FormInstance>;
  submitText?:     string;
  cancelText?:     string;
  modalProps?:     {
    open: boolean;
    title: string;
    width?: number;
    destroyOnHidden?: boolean;
  };
}

function renderControl(schema: FormFieldSchema): React.ReactNode {
  const common = { placeholder: schema.placeholder, disabled: schema.disabled };

  switch (schema.type) {
    case 'input':
      return <Input {...common} />;
    case 'password':
      return <Input.Password {...common} />;
    case 'textarea':
      return <Input.TextArea {...common} rows={schema.rows ?? 3} />;
    case 'select':
      return <Select {...common} options={schema.options} mode={schema.mode} allowClear />;
    case 'number':
      return (
        <InputNumber
          {...common}
          min={schema.min}
          max={schema.max}
          step={schema.step}
          style={{ width: '100%' }}
        />
      );
    case 'date':
      return <DatePicker {...common} style={{ width: '100%' }} />;
    case 'switch':
      return <Switch disabled={schema.disabled} />;
    case 'radio':
      return (
        <Radio.Group disabled={schema.disabled}>
          {schema.options?.map((opt) => (
            <Radio key={opt.value} value={opt.value}>{opt.label}</Radio>
          ))}
        </Radio.Group>
      );
    case 'custom':
      return schema.component ? React.createElement(schema.component) : null;
    default:
      return <Input {...common} />;
  }
}

function SchemaForm({
  schema,
  initialValues,
  onSubmit,
  onSuccess,
  onCancel,
  loading = false,
  layout = 'vertical',
  formRef,
  submitText = '确定',
  cancelText = '取消',
  modalProps,
}: SchemaFormProps) {
  const [form] = Form.useForm();

  React.useImperativeHandle(formRef, () => form, [form]);

  const handleFinish = async (values: Record<string, unknown>) => {
    await onSubmit(values);
    onSuccess?.();
  };

  const formContent = (
    <Form
      form={form}
      layout={layout}
      initialValues={initialValues}
      onFinish={handleFinish}
      disabled={loading}
    >
      {schema.fields.map((f) => (
        <Form.Item
          key={f.name}
          name={f.name}
          label={f.label}
          valuePropName={f.type === 'switch' ? 'checked' : 'value'}
          rules={
            f.required
              ? [{ required: true, message: `请输入${f.label}` }, ...(f.rules ?? [])]
              : f.rules
          }
        >
          {renderControl(f)}
        </Form.Item>
      ))}

      {/* Modal 模式下不渲染提交按钮（由 Modal.onOk 触发） */}
      {!modalProps && (
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              {submitText}
            </Button>
            {onCancel && (
              <Button onClick={onCancel}>{cancelText}</Button>
            )}
          </Space>
        </Form.Item>
      )}
    </Form>
  );

  if (modalProps) {
    return (
      <Modal
        title={modalProps.title}
        open={modalProps.open}
        onOk={() => form.submit()}
        onCancel={onCancel}
        confirmLoading={loading}
        width={modalProps.width}
        destroyOnHidden={modalProps.destroyOnHidden}
      >
        {formContent}
      </Modal>
    );
  }

  return formContent;
}

export default SchemaForm;
