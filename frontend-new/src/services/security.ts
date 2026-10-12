import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { get, post, put } from './api-client';

export interface OverviewItem {
  rule_id: string;
  severity: string;
  violation_count: number;
  status: string;
}

export interface SecurityOverview {
  compliance: { total: number; ok: number; violated: number };
  items: OverviewItem[];
}

export type PolicyValue = string | number | boolean | string[] | null;

export interface SecurityPolicyItem {
  key: string;
  value: PolicyValue;
  default: PolicyValue;
  type: string;
  min: number | null;
  max: number | null;
  choices: string[];
  description: string;
  tag: string;
  editable?: boolean;
  version?: number | null;
}

export interface SecurityFindingRow {
  id: number;
  rule_id: string;
  severity: string;
  subject_type: string;
  subject_id: number;
  status: string;
  detail?: Record<string, unknown>;
  first_seen?: string;
  last_seen?: string;
}

export interface RemoteLoginRow {
  user_id: number;
  ip: string;
  username: string;
  count: number;
  last_time: string | null;
}

export interface ScanResult {
  findings: Array<Record<string, unknown>>;
  summary?: Record<string, number>;
  skipped?: boolean;
}

export const securityKeys = {
  all: ['security'] as const,
  overview: ['security', 'overview'] as const,
  policies: ['security', 'policies'] as const,
  findings: (params: Record<string, unknown>) => ['security', 'findings', params] as const,
  remoteLogins: (params: Record<string, unknown>) => ['security', 'remote-logins', params] as const
};

export function useSecurityOverview() {
  return useQuery({
    queryKey: securityKeys.overview,
    queryFn: async () =>
      (await get<SecurityOverview>('/security/overview')).data ?? {
        compliance: { total: 0, ok: 0, violated: 0 },
        items: []
      }
  });
}

export function useSecurityFindings(params: Record<string, unknown>) {
  return useQuery({
    queryKey: securityKeys.findings(params),
    queryFn: async () =>
      (await get<{ items: SecurityFindingRow[]; total: number }>('/security/findings', params))
        .data ?? { items: [], total: 0 }
  });
}

export function useSecurityPolicies() {
  return useQuery({
    queryKey: securityKeys.policies,
    queryFn: async () =>
      (await get<{ items: SecurityPolicyItem[] }>('/security/policies')).data ?? { items: [] }
  });
}

export function useUpdatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value, version }: { key: string; value: PolicyValue; version?: number }) =>
      put(`/security/policies/${key}`, { value, version }),
    onSuccess: () => qc.invalidateQueries({ queryKey: securityKeys.all })
  });
}

export function useSecurityScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dryRun: boolean = false) =>
      (await post<ScanResult>('/security/scan', { dry_run: dryRun })).data ?? { findings: [] },
    onSuccess: (_data, dryRun) => {
      if (!dryRun) qc.invalidateQueries({ queryKey: securityKeys.all });
    }
  });
}

export function useRemoteLogins(params: Record<string, unknown>) {
  return useQuery({
    queryKey: securityKeys.remoteLogins(params),
    queryFn: async () =>
      (
        await get<{ items: RemoteLoginRow[]; total: number; enabled: boolean }>(
          '/security/remote-logins',
          params
        )
      ).data ?? { items: [], total: 0, enabled: false }
  });
}

export function useLockAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, reason }: { userId: number; reason: string }) =>
      post(`/security/users/${userId}/lock`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: securityKeys.all })
  });
}

export function useUnlockAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: number) => post(`/security/users/${userId}/unlock`),
    onSuccess: () => qc.invalidateQueries({ queryKey: securityKeys.all })
  });
}
