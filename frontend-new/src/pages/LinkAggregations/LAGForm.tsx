/**
 * 链路聚合组创建表单（Modal）
 * - 使用 SchemaForm 声明式驱动 + modalProps 自动包裹 Modal
 * - 仅创建模式（无编辑）
 * - 交换机选项仅显示非管理型
 */
import { useMemo } from 'react';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm';
import { useCreateLinkAggregationGroup } from '@/services/link-aggregation';
import { useSwitchList } from '@/services/switch';
import { useMessage } from '@/hooks/useMessage';

interface LAGFormProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

function useLAGFormSchema() {
  const { data: switchList } = useSwitchList();

  const unmanagedSwitchOptions = useMemo(
    () =>
      (switchList?.items ?? [])
        .filter((sw: any) => !sw.has_ssh)
        .map((sw: any) => ({ label: sw.name || sw.ip, value: sw.id })),
    [switchList]
  );

  const schema: FormSchema = useMemo(
    () => ({
      fields: [
        {
          name: 'device_id',
          label: '交换机',
          type: 'select',
          required: true,
          placeholder: '请选择交换机',
          options: unmanagedSwitchOptions
        },
        {
          name: 'lag_name',
          label: '聚合组名称',
          type: 'input',
          required: true,
          placeholder: '如: Eth-Trunk1'
        },
        {
          name: 'lag_type',
          label: '聚合类型',
          type: 'select',
          required: true,
          options: [
            { label: 'LACP（动态）', value: 'lacp' },
            { label: '静态', value: 'static' }
          ]
        }
      ]
    }),
    [unmanagedSwitchOptions]
  );

  return schema;
}

function LAGForm({ open, onCancel, onSuccess }: LAGFormProps) {
  const schema = useLAGFormSchema();
  const createLag = useCreateLinkAggregationGroup();
  const message = useMessage();

  const handleSubmit = async (values: Record<string, unknown>) => {
    await createLag.mutateAsync({
      deviceId: values.device_id as number,
      data: {
        lag_name: values.lag_name as string,
        lag_type: values.lag_type as 'lacp' | 'static'
      }
    });
    message.success('链路聚合组已创建');
  };

  return (
    <SchemaForm
      schema={schema}
      onSubmit={handleSubmit}
      onSuccess={onSuccess}
      onCancel={onCancel}
      loading={createLag.isPending}
      modalProps={{
        open,
        title: '创建链路聚合组',
        destroyOnHidden: true
      }}
    />
  );
}

export default LAGForm;
