import type { GlobalToken } from 'antd';

function normalize(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

export function severityColor(
  severity: string | null | undefined,
  token: GlobalToken
): string | undefined {
  switch (normalize(severity)) {
    case 'critical':
    case 'crit':
    case 'fatal':
      return token.colorError;
    case 'warning':
    case 'warn':
      return token.colorWarning;
    case 'info':
    case 'information':
      return token.colorInfo;
    case 'ok':
    case 'normal':
      return token.colorSuccess;
    default:
      return undefined;
  }
}

export function deliveryStatusColor(
  status: string | null | undefined,
  token: GlobalToken
): string | undefined {
  switch (normalize(status)) {
    case 'pending':
    case 'queued':
      return token.colorBorder;
    case 'sent':
    case 'success':
    case 'delivered':
      return token.colorSuccess;
    case 'failed':
    case 'error':
      return token.colorError;
    default:
      return undefined;
  }
}

export function portStatusBgColor(
  status: string | null | undefined,
  token: GlobalToken
): string | undefined {
  switch (normalize(status)) {
    case 'free':
      return token.colorSuccess;
    case 'occupied':
      return token.colorPrimary;
    case 'disabled':
      return token.colorTextQuaternary;
    case 'error':
      return token.colorError;
    default:
      return undefined;
  }
}

export function monitorProtocolColor(
  protocol: string | null | undefined,
  token: GlobalToken
): string | undefined {
  switch (normalize(protocol)) {
    case 'snmp':
      return token.colorPrimary;
    case 'ipmi':
      return token.colorPrimaryActive;
    case 'zabbix':
      return token.colorWarning;
    case 'ping':
      return token.colorSuccess;
    default:
      return undefined;
  }
}

export function incidentStatusTagColor(status: string | null | undefined): string {
  switch (normalize(status)) {
    case 'active':
      return 'processing';
    case 'acknowledged':
      return 'warning';
    default:
      return 'default';
  }
}
