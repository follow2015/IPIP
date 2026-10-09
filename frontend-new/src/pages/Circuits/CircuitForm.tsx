import { useMemo } from 'react';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm';
import { BandwidthPairInput } from '@/components/BandwidthInput';
import {
  useCreateCircuit,
  useUpdateCircuit,
  type Circuit,
  type CircuitPayload
} from '@/services/circuit';
import { useCarrierOptions } from '@/services/carrier';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks/useMessage';

interface CircuitFormProps {
  open: boolean;
  record?: Circuit | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const DATE_FIELDS = ['start_date', 'end_date'] as const;

function toPayload(values: Record<string, unknown>): CircuitPayload {
  const payload: Record<string, unknown> = { ...values };

  const pair = payload.bandwidth_and_committed as
    | {
        bandwidth?: {
          bandwidth_value?: number | null;
          bandwidth_unit?: string | null;
          bandwidth_mbps?: number | null;
        };
        committed?: {
          committed_value?: number | null;
          committed_unit?: string | null;
          committed_mbps?: number | null;
        };
      }
    | undefined;
  delete payload.bandwidth_and_committed;
  if (pair) {
    const bw = pair.bandwidth ?? {};
    payload.bandwidth_value = bw.bandwidth_value ?? null;
    payload.bandwidth_unit = bw.bandwidth_unit ?? null;
    payload.bandwidth_mbps = bw.bandwidth_mbps ?? null;
    const cm = pair.committed ?? {};
    payload.committed_value = cm.committed_value ?? null;
    payload.committed_unit = cm.committed_unit ?? null;
    payload.committed_mbps = cm.committed_mbps ?? null;
  }

  for (const key of DATE_FIELDS) {
    const v = payload[key];
    payload[key] = v ? (v as Dayjs).format('YYYY-MM-DD') : null;
  }

  return payload as CircuitPayload;
}

function CircuitForm({ open, record, onCancel, onSuccess }: CircuitFormProps) {
  const { t } = useTranslation('circuit');
  const { t: tc } = useTranslation('common');
  const createCircuit = useCreateCircuit();
  const updateCircuit = useUpdateCircuit();
  const message = useMessage();

  const { data: carrierOptions } = useCarrierOptions();
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const isEdit = !!record;

  const schema: FormSchema = useMemo(
    () => ({
      fields: [
        {
          name: 'circuit_no',
          label: t('field.circuitNo'),
          type: 'input',
          required: true,
          placeholder: t('field.circuitNo')
        },
        { name: 'name', label: t('field.name'), type: 'input' },
        {
          name: 'carrier_id',
          label: t('field.carrier'),
          type: 'select',
          options: carrierOptions ?? []
        },
        {
          name: 'customer_id',
          label: t('field.customer'),
          type: 'select',
          options: customerOptions ?? []
        },
        {
          name: 'status',
          label: t('field.status'),
          type: 'select',
          defaultValue: 'active',
          options: (['pending', 'active', 'fault', 'suspended', 'terminated'] as const).map(
            (v) => ({
              label: t(`status.${v}`),
              value: v
            })
          )
        },
        {
          name: 'billing_mode',
          label: t('field.billingMode'),
          type: 'select',
          options: (['flat', 'commit_95', 'commit_peak', 'commit_avg', 'per_gb'] as const).map(
            (v) => ({
              label: t(`billingMode.${v}`),
              value: v
            })
          )
        },
        {
          name: 'bandwidth_and_committed',
          label: t('field.bandwidth'),
          type: 'custom',
          component: BandwidthPairInput
        },
        { name: 'monthly_fee', label: t('field.monthlyFee'), type: 'number', min: 0, step: 0.01 },
        {
          name: 'overage_unit_price',
          label: t('field.overagePrice'),
          type: 'number',
          min: 0,
          step: 0.0001
        },
        {
          name: 'traffic_unit_price',
          label: t('field.trafficPrice'),
          type: 'number',
          min: 0,
          step: 0.0001
        },
        { name: 'sla_level', label: t('field.sla'), type: 'input' },
        { name: 'access_type', label: t('field.accessType'), type: 'input' },
        { name: 'start_date', label: t('field.startDate'), type: 'date' },
        { name: 'end_date', label: t('field.endDate'), type: 'date' },
        { name: 'contract_no', label: t('field.contractNo'), type: 'input' },
        { name: 'a_end_desc', label: t('field.aEnd'), type: 'input' },
        { name: 'z_end_desc', label: t('field.zEnd'), type: 'input' },
        { name: 'notes', label: t('field.notes'), type: 'textarea', rows: 3 }
      ]
    }),
    [carrierOptions, customerOptions, t]
  );

  const initialValues = useMemo(() => {
    if (!record) return undefined;
    return {
      circuit_no: record.circuit_no,
      name: record.name ?? undefined,
      carrier_id: record.carrier_id ?? undefined,
      customer_id: record.customer_id ?? undefined,
      status: record.status ?? undefined,
      billing_mode: record.billing_mode ?? undefined,
      bandwidth_and_committed: {
        bandwidth:
          record.bandwidth_mbps != null ? { bandwidth_mbps: record.bandwidth_mbps } : undefined,
        committed:
          record.committed_mbps != null ? { committed_mbps: record.committed_mbps } : undefined
      },
      monthly_fee: record.monthly_fee ?? undefined,
      overage_unit_price: record.overage_unit_price ?? undefined,
      traffic_unit_price: record.traffic_unit_price ?? undefined,
      sla_level: record.sla_level ?? undefined,
      access_type: record.access_type ?? undefined,
      start_date: record.start_date ? dayjs(record.start_date) : undefined,
      end_date: record.end_date ? dayjs(record.end_date) : undefined,
      contract_no: record.contract_no ?? undefined,
      a_end_desc: record.a_end_desc ?? undefined,
      z_end_desc: record.z_end_desc ?? undefined,
      notes: record.notes ?? undefined
    };
  }, [record]);

  const handleSubmit = async (values: Record<string, unknown>) => {
    const payload = toPayload(values);
    if (isEdit && record) {
      await updateCircuit.mutateAsync({ id: record.id, data: payload });
      message.success(t('message.updateSuccess'));
    } else {
      await createCircuit.mutateAsync(payload);
      message.success(t('message.createSuccess'));
    }
  };

  return (
    <SchemaForm
      schema={schema}
      initialValues={initialValues}
      onSubmit={handleSubmit}
      onSuccess={onSuccess}
      onCancel={onCancel}
      loading={createCircuit.isPending || updateCircuit.isPending}
      modalProps={{
        open,
        title: isEdit ? `${tc('action.edit')} · ${record?.circuit_no ?? ''}` : t('action.add'),
        width: 640,
        destroyOnHidden: true
      }}
    />
  );
}

export default CircuitForm;
