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
import { useTranslation } from 'react-i18next';

interface LAGFormProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

function useLAGFormSchema() {
  const { t: td } = useTranslation('device');
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
          label: td('deviceSubtype.SWITCH'),
          type: 'select',
          required: true,
          placeholder: td('lag.form.selectSwitch'),
          options: unmanagedSwitchOptions
        },
        {
          name: 'lag_name',
          label: td('lag.column.lagName'),
          type: 'input',
          required: true,
          placeholder: td('lag.form.lagNamePlaceholder')
        },
        {
          name: 'lag_type',
          label: td('lag.form.lagType'),
          type: 'select',
          required: true,
          options: [
            { label: td('lag.type.lacpDynamic'), value: 'lacp' },
            { label: td('lag.type.static'), value: 'static' }
          ]
        }
      ]
    }),
    [unmanagedSwitchOptions, td]
  );

  return schema;
}

function LAGForm({ open, onCancel, onSuccess }: LAGFormProps) {
  const { t: td } = useTranslation('device');
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
    message.success(td('lag.message.created'));
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
        title: td('lag.action.create'),
        destroyOnHidden: true
      }}
    />
  );
}

export default LAGForm;
