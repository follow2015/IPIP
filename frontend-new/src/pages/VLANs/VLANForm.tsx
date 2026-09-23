/**
 * VLAN 创建表单（Modal）
 * - 纯创建、无回填，故裸用 SchemaForm（与 LAGForm 同范式），不混 useCrudForm
 * - 说明：useCrudForm 仅在表单需要「编辑回填」(create+update 双路径) 时才有价值；
 *   VLANs 页面无编辑入口，VLANForm 永远是纯新增，套 useCrudForm 属过度设计。
 * - 字段含动态机房/交换机/状态选项，在组件内通过 hook 生成 schema。
 */
import { useMemo } from 'react';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm';
import { useCreateVLAN, type CreateVLANRequest } from '@/services/vlan';
import { useRoomOptions } from '@/services/room';
import { useSwitchList } from '@/services/switch';
import { getVlanStatusOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';

interface VLANFormProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

function useVLANFormSchema() {
  const { t } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { data: roomOptions } = useRoomOptions();
  const { data: switchList } = useSwitchList();

  const unmanagedSwitchOptions = useMemo(
    () =>
      (switchList?.items ?? [])
        .filter((sw: any) => !sw.has_ssh)
        .map((sw: any) => ({ label: sw.name || sw.ip, value: sw.id })),
    [switchList]
  );

  const statusOptions = useMemo(() => getVlanStatusOptions(t), [t]);

  const schema: FormSchema = useMemo(
    () => ({
      fields: [
        {
          name: 'vlan_id',
          label: 'VLAN ID',
          type: 'number',
          required: true,
          min: 1,
          max: 4094,
          placeholder: '1-4094'
        },
        {
          name: 'name',
          label: tc('field.name'),
          type: 'input',
          required: true,
          placeholder: t('vlan.form.inputName')
        },
        {
          name: 'purpose',
          label: tc('field.purpose'),
          type: 'input',
          placeholder: t('vlan.form.inputPurpose')
        },
        {
          name: 'device_id',
          label: t('vlan.form.switch'),
          type: 'select',
          required: true,
          placeholder: t('vlan.form.selectSwitch'),
          options: unmanagedSwitchOptions
        },
        {
          name: 'room_id',
          label: t('vlan.form.room'),
          type: 'select',
          placeholder: t('vlan.form.selectRoom'),
          options: roomOptions ?? []
        },
        {
          name: 'status',
          label: tc('field.status'),
          type: 'select',
          placeholder: t('vlan.form.selectStatus'),
          options: statusOptions
        }
      ]
    }),
    [unmanagedSwitchOptions, roomOptions, statusOptions, t, tc]
  );

  return schema;
}

function VLANForm({ open, onCancel, onSuccess }: VLANFormProps) {
  const { t } = useTranslation('device');
  const schema = useVLANFormSchema();
  const createVLAN = useCreateVLAN();
  const message = useMessage();

  const handleSubmit = async (values: Record<string, unknown>) => {
    await createVLAN.mutateAsync(values as CreateVLANRequest);
    message.success(t('vlan.message.created'));
  };

  return (
    <SchemaForm
      schema={schema}
      onSubmit={handleSubmit}
      onSuccess={onSuccess}
      onCancel={onCancel}
      loading={createVLAN.isPending}
      modalProps={{
        open,
        title: t('vlan.action.add'),
        width: 520,
        destroyOnHidden: true
      }}
    />
  );
}

export default VLANForm;
