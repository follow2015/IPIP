import { useMemo } from 'react';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm';
import { useCreateCarrier, type CarrierPayload } from '@/services/carrier';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';

interface CarrierFormProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

function CarrierForm({ open, onCancel, onSuccess }: CarrierFormProps) {
  const { t } = useTranslation('circuit');
  const createCarrier = useCreateCarrier();
  const message = useMessage();

  const schema: FormSchema = useMemo(
    () => ({
      fields: [
        {
          name: 'name',
          label: t('carrier.field.name'),
          type: 'input',
          required: true,
          placeholder: t('carrier.field.name')
        },
        {
          name: 'short_name',
          label: t('carrier.field.shortName'),
          type: 'input',
          placeholder: t('carrier.field.shortName')
        },
        {
          name: 'carrier_type',
          label: t('carrier.field.type'),
          type: 'select',
          options: (['basic', 'isp', 'idc', 'agent'] as const).map((v) => ({
            label: t(`carrier.type.${v}`),
            value: v
          }))
        },
        {
          name: 'status',
          label: t('carrier.field.status'),
          type: 'select',
          defaultValue: 'active',
          options: (['active', 'inactive'] as const).map((v) => ({
            label: t(`carrier.status.${v}`),
            value: v
          }))
        },
        {
          name: 'contact_person',
          label: t('carrier.field.contactPerson'),
          type: 'input'
        },
        {
          name: 'contact_phone',
          label: t('carrier.field.contactPhone'),
          type: 'input'
        },
        {
          name: 'hotline',
          label: t('carrier.field.hotline'),
          type: 'input'
        },
        {
          name: 'email',
          label: t('carrier.field.email'),
          type: 'input'
        },
        {
          name: 'default_sla_level',
          label: t('carrier.field.sla'),
          type: 'input'
        },
        {
          name: 'qualification_no',
          label: t('carrier.field.qualificationNo'),
          type: 'input'
        },
        { name: 'notes', label: t('carrier.field.notes'), type: 'textarea', rows: 3 }
      ]
    }),
    [t]
  );

  const handleSubmit = async (values: Record<string, unknown>) => {
    await createCarrier.mutateAsync(values as CarrierPayload);
    message.success(t('message.createSuccess'));
  };

  return (
    <SchemaForm
      schema={schema}
      onSubmit={handleSubmit}
      onSuccess={onSuccess}
      onCancel={onCancel}
      loading={createCarrier.isPending}
      modalProps={{
        open,
        title: t('carrier.action.add'),
        width: 560,
        destroyOnHidden: true
      }}
    />
  );
}

export default CarrierForm;
