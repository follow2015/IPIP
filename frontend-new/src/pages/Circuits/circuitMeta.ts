import type { BillingMode, CircuitStatus } from '@/services/circuit';

export const CIRCUIT_STATUS_COLOR: Record<CircuitStatus, string> = {
  pending: 'blue',
  active: 'green',
  fault: 'red',
  suspended: 'orange',
  terminated: 'default'
};

export const CIRCUIT_STATUS_KEY = {
  pending: 'status.pending',
  active: 'status.active',
  fault: 'status.fault',
  suspended: 'status.suspended',
  terminated: 'status.terminated'
} as const satisfies Record<CircuitStatus, string>;

export const BILLING_MODE_KEY = {
  flat: 'billingMode.flat',
  commit_95: 'billingMode.commit_95',
  commit_peak: 'billingMode.commit_peak',
  commit_avg: 'billingMode.commit_avg',
  per_gb: 'billingMode.per_gb'
} as const satisfies Record<BillingMode, string>;

export const CIRCUIT_STATUS_VALUES = Object.keys(CIRCUIT_STATUS_KEY) as CircuitStatus[];


export type AnchorState = 'managed' | 'notManaged' | 'lost';

export const ANCHOR_TAG_COLOR: Record<AnchorState, string> = {
  managed: 'success',
  notManaged: 'default',
  lost: 'error'
};

export interface AnchorLike {
  connection_id: number | null;
  anchor_lost: boolean;
}

export function resolveAnchorState(seg: AnchorLike): AnchorState {
  if (seg.anchor_lost) return 'lost';
  if (seg.connection_id == null) return 'notManaged';
  return 'managed';
}

export const BILLING_MODE_VALUES = Object.keys(BILLING_MODE_KEY) as BillingMode[];
