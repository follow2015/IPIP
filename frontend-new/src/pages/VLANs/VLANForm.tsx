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
import { VLAN_STATUS_MAP } from '@/types/enums';
import { useMessage } from '@/hooks/useMessage';

interface VLANFormProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}


function useVLANFormSchema() {
  const { data: roomOptions } = useRoomOptions();
  const { data: switchList } = useSwitchList();

  
  const unmanagedSwitchOptions = useMemo(
    () =>
      (switchList?.items ?? [])
        .filter((sw: any) => !sw.has_ssh)
        .map((sw: any) => ({ label: sw.name || sw.ip, value: sw.id })),
    [switchList]
  );

  const statusOptions = useMemo(
    () =>
      Object.entries(VLAN_STATUS_MAP).map(([k, v]) => ({
        label: v.label,
        value: Number(k)
      })),
    []
  );

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
          label: '名称',
          type: 'input',
          required: true,
          placeholder: '请输入 VLAN 名称'
        },
        {
          name: 'purpose',
          label: '用途',
          type: 'input',
          placeholder: '请输入用途'
        },
        {
          name: 'device_id',
          label: '所属交换机',
          type: 'select',
          required: true,
          placeholder: '请选择交换机',
          options: unmanagedSwitchOptions
        },
        {
          name: 'room_id',
          label: '所属机房',
          type: 'select',
          placeholder: '请选择机房',
          options: roomOptions ?? []
        },
        {
          name: 'status',
          label: '状态',
          type: 'select',
          placeholder: '请选择状态',
          options: statusOptions
        }
      ]
    }),
    [unmanagedSwitchOptions, roomOptions, statusOptions]
  );

  return schema;
}


function VLANForm({ open, onCancel, onSuccess }: VLANFormProps) {
  const schema = useVLANFormSchema();
  const createVLAN = useCreateVLAN();
  const message = useMessage();

  const handleSubmit = async (values: Record<string, unknown>) => {
    await createVLAN.mutateAsync(values as CreateVLANRequest);
    message.success('VLAN 已创建');
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
        title: '新增 VLAN',
        width: 520,
        destroyOnHidden: true
      }}
    />
  );
}

export default VLANForm;
