
export type SecurityRuleLabelKey =
  | 'rules.user.password_expired'
  | 'rules.user.password_never_changed'
  | 'rules.user.dormant_account'
  | 'rules.snmp.v2c_in_use'
  | 'rules.snmp.default_community'
  | 'rules.login.remote_access'
  | 'rules.login.brute_force_stats'
  | 'rules.system.audit_retention';

export const SECURITY_RULE_LABEL_KEYS: Record<string, SecurityRuleLabelKey> = {
  'user.password_expired': 'rules.user.password_expired',
  'user.password_never_changed': 'rules.user.password_never_changed',
  'user.dormant_account': 'rules.user.dormant_account',
  'snmp.v2c_in_use': 'rules.snmp.v2c_in_use',
  'snmp.default_community': 'rules.snmp.default_community',
  'login.remote_access': 'rules.login.remote_access',
  'login.brute_force_stats': 'rules.login.brute_force_stats',
  'system.audit_retention': 'rules.system.audit_retention'
};

export type SecuritySeverityLabelKey =
  'severity.critical' | 'severity.high' | 'severity.medium' | 'severity.low';

export const SECURITY_SEVERITY_LABEL_KEYS: Record<string, SecuritySeverityLabelKey> = {
  critical: 'severity.critical',
  high: 'severity.high',
  medium: 'severity.medium',
  low: 'severity.low'
};

export type SecurityStatusLabelKey = 'status.ok' | 'status.open';

export const SECURITY_STATUS_LABEL_KEYS: Record<string, SecurityStatusLabelKey> = {
  ok: 'status.ok',
  open: 'status.open'
};

export type SecurityPolicyLabelKey =
  | 'policyNames.password.min_length'
  | 'policyNames.password.require_classes'
  | 'policyNames.password.max_age_days'
  | 'policyNames.password.min_age_days'
  | 'policyNames.password.expire_warn_days'
  | 'policyNames.password.force_change_on_reset'
  | 'policyNames.snmp.allowed_versions'
  | 'policyNames.snmp.forbid_default_community'
  | 'policyNames.snmp.mode'
  | 'policyNames.login.remote_access'
  | 'policyNames.login.trusted_networks'
  | 'policyNames.login.brute_force_threshold'
  | 'policyNames.login.brute_force_window_hours'
  | 'policyNames.user.dormant_days'
  | 'policyNames.audit.retention_days';

export const SECURITY_POLICY_LABEL_KEYS: Record<string, SecurityPolicyLabelKey> = {
  'password.min_length': 'policyNames.password.min_length',
  'password.require_classes': 'policyNames.password.require_classes',
  'password.max_age_days': 'policyNames.password.max_age_days',
  'password.min_age_days': 'policyNames.password.min_age_days',
  'password.expire_warn_days': 'policyNames.password.expire_warn_days',
  'password.force_change_on_reset': 'policyNames.password.force_change_on_reset',
  'snmp.allowed_versions': 'policyNames.snmp.allowed_versions',
  'snmp.forbid_default_community': 'policyNames.snmp.forbid_default_community',
  'snmp.mode': 'policyNames.snmp.mode',
  'login.remote_access.mode': 'policyNames.login.remote_access',
  'login.trusted_networks': 'policyNames.login.trusted_networks',
  'login.brute_force_threshold': 'policyNames.login.brute_force_threshold',
  'login.brute_force_window_hours': 'policyNames.login.brute_force_window_hours',
  'user.dormant_days': 'policyNames.user.dormant_days',
  'audit.retention_days': 'policyNames.audit.retention_days'
};

export type SecurityValueLabelKey = 'values.on' | 'values.off' | 'values.audit' | 'values.enforce';

export const SECURITY_VALUE_LABEL_KEYS: Record<string, SecurityValueLabelKey> = {
  on: 'values.on',
  off: 'values.off',
  audit: 'values.audit',
  enforce: 'values.enforce'
};

export type SecurityLabelKey =
  | SecurityRuleLabelKey
  | SecuritySeverityLabelKey
  | SecurityStatusLabelKey
  | SecurityPolicyLabelKey
  | SecurityValueLabelKey;
