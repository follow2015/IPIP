
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post } from '../api-client';
import { createCrudHooks } from '../crud-factory';
import { queryKeys } from '../query-keys';

import type { PaginatedData, PaginationParams } from '@/types/api';
import type { components } from '@/types/api-generated';

export type MonitorSilenceRule = Required<components['schemas']['MonitorSilenceRuleItem']>;

export interface MonitorSilenceRuleInput {
  name: string;
  device_ids?: number[] | null;
  alert_types?: string[] | null;
  silence_from: string;
  silence_until: string;
  reason?: string;
  enabled?: boolean;
}

const silenceRuleHooks = createCrudHooks<
  MonitorSilenceRule,
  MonitorSilenceRuleInput,
  Partial<MonitorSilenceRuleInput> & { id: number }
>({
  basePath: '/monitor/silence-rules',
  queryKey: queryKeys.monitor.silenceRulesCrud
});

export const useSilenceRules = silenceRuleHooks.useList;
export const useCreateSilenceRule = silenceRuleHooks.useCreate;
export const useUpdateSilenceRule = silenceRuleHooks.useUpdate;
export const useDeleteSilenceRule = silenceRuleHooks.useDelete;

export type MonitorAlertDependencyRule = Required<
  components['schemas']['MonitorAlertDependencyRuleItem']
>;

export interface MonitorAlertDependencyRuleInput {
  name: string;
  upstream_device_id: number;
  downstream_device_id: number;
  alert_types?: string[] | null;
  reason?: string;
  enabled?: boolean;
}

const alertDependencyRuleHooks = createCrudHooks<
  MonitorAlertDependencyRule,
  MonitorAlertDependencyRuleInput,
  Partial<MonitorAlertDependencyRuleInput> & { id: number }
>({
  basePath: '/monitor/alert-dependency-rules',
  queryKey: queryKeys.monitor.alertDependencyRulesCrud
});

export const useAlertDependencyRules = alertDependencyRuleHooks.useList;
export const useCreateAlertDependencyRule = alertDependencyRuleHooks.useCreate;
export const useUpdateAlertDependencyRule = alertDependencyRuleHooks.useUpdate;
export const useDeleteAlertDependencyRule = alertDependencyRuleHooks.useDelete;

export type MonitorSlaTarget = Required<components['schemas']['MonitorSlaTargetItem']>;
export type MonitorSlaAchievement = components['schemas']['MonitorSlaAchievement'];

export interface MonitorSlaTargetInput {
  name: string;
  target_device_ids: number[];
  target_ratio: number;
  window_days?: number;
  description?: string;
  enabled?: boolean;
}

const slaTargetHooks = createCrudHooks<
  MonitorSlaTarget,
  MonitorSlaTargetInput,
  Partial<MonitorSlaTargetInput> & { id: number }
>({
  basePath: '/monitor/sla-targets',
  queryKey: queryKeys.monitor.slaTargetsCrud
});

export const useSlaTargets = slaTargetHooks.useList;
export const useCreateSlaTarget = slaTargetHooks.useCreate;
export const useUpdateSlaTarget = slaTargetHooks.useUpdate;
export const useDeleteSlaTarget = slaTargetHooks.useDelete;

export function useSlaAchievements(start?: string, end?: string) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const qs = params.toString() ? `?${params.toString()}` : '';
  return useQuery({
    queryKey: [...queryKeys.monitor.slaAchievements, start, end],
    queryFn: async () => {
      const res = await get<PaginatedData<MonitorSlaAchievement>>(
        `/monitor/sla-targets/achievements${qs}`
      );
      return res.data;
    }
  });
}

export type DeviceMetricOverride = Required<components['schemas']['DeviceMetricOverrideItem']>;

export interface DeviceMetricOverrideInput {
  device_id: number;
  metric_key: string;
  threshold: Record<string, unknown>;
  enabled?: boolean;
  note?: string;
}

export interface ThresholdOverrideQueryParams extends PaginationParams {
  device_id?: number;
  metric_key?: string;
}

const thresholdOverrideHooks = createCrudHooks<
  DeviceMetricOverride,
  DeviceMetricOverrideInput,
  DeviceMetricOverrideInput & { id: number },
  ThresholdOverrideQueryParams
>({
  basePath: '/monitor/threshold-overrides',
  queryKey: queryKeys.monitor.thresholdOverridesCrud
});

export const useThresholdOverrides = thresholdOverrideHooks.useList;

export function useUpsertThresholdOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: DeviceMetricOverrideInput) => {
      const res = await post<DeviceMetricOverride>('/monitor/threshold-overrides', input);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.monitor.thresholdOverridesCrud })
  });
}

export const useDeleteThresholdOverride = thresholdOverrideHooks.useDelete;

export type MonitorEscalationPolicy = Required<
  components['schemas']['MonitorEscalationPolicyItem']
>;

export interface MonitorEscalationStepInput {
  step_no?: number;
  wait_minutes: number;
  escalate_severity?: string | null;
  escalate_to_role_id?: number | null;
  escalate_webhook_url?: string | null;
  enabled?: boolean;
}

export interface MonitorEscalationPolicyInput {
  name: string;
  alert_type?: string | null;
  severity?: string | null;
  wait_minutes: number;
  escalate_severity?: string | null;
  escalate_to_role_id?: number | null;
  escalate_webhook_url?: string | null;
  repeat_minutes?: number;
  enabled?: boolean;
  steps?: MonitorEscalationStepInput[] | null;
}

const escalationPolicyHooks = createCrudHooks<
  MonitorEscalationPolicy,
  MonitorEscalationPolicyInput,
  Partial<MonitorEscalationPolicyInput> & { id: number }
>({
  basePath: '/monitor/escalation-policies',
  queryKey: queryKeys.monitor.escalationPoliciesCrud
});

export const useEscalationPolicies = escalationPolicyHooks.useList;
export const useCreateEscalationPolicy = escalationPolicyHooks.useCreate;
export const useUpdateEscalationPolicy = escalationPolicyHooks.useUpdate;
export const useDeleteEscalationPolicy = escalationPolicyHooks.useDelete;
