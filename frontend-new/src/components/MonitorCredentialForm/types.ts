import type { FormInstance } from 'antd';


export type MonitorProtocol = 'snmp' | 'ipmi' | 'zabbix';


export interface MonitorCredentialFormProps {
  
  protocol: string;
  
  mode: 'create' | 'edit';
  
  payloadMeta?: Record<string, unknown>;
  
  form: FormInstance;
  
  onValuesChange?: (
    changedValues: Record<string, unknown>,
    allValues: Record<string, unknown>
  ) => void;
}


export const SNMP_VERSION_OPTIONS = [
  { value: 'v2c', label: 'v2c' },
  { value: 'v3', label: 'v3' }
];


export const AUTH_PROTOCOL_OPTIONS = [
  { value: 'sha', label: 'SHA' },
  { value: 'sha256', label: 'SHA-256' },
  { value: 'sha512', label: 'SHA-512' },
  { value: 'md5', label: 'MD5' },
  { value: 'none', label: '无' }
];


export const PRIV_PROTOCOL_OPTIONS = [
  { value: 'aes', label: 'AES' },
  { value: 'aes256', label: 'AES-256' },
  { value: 'des', label: 'DES' },
  { value: '3des', label: '3DES' },
  { value: 'none', label: '无' }
];


export const MATCH_BY_OPTIONS = [
  { value: 'host', label: '主机名' },
  { value: 'ip', label: 'IP 地址' }
];
