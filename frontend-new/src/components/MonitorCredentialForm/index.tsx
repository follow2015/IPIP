/**
 * 共享监控凭据结构化表单（P2-9）。
 *
 * 按 protocol 渲染对应子表单（SNMP / IPMI / Zabbix），
 * 供「凭据管理页」与「设备详情 CredentialTab」复用，消除 JSON TextArea 输入方式不一致。
 *
 * 组件本身不渲染外层 <Form> —— 由调用方持有 <Form form={form}> 包裹，
 * 这样 protocol / name / 提交逻辑都可由调用方控制（v1.2 M-8）。
 * 各子表单通过 Form 上下文的 Form.useWatch 响应式切换字段。
 */
import SnmpForm from './SnmpForm';
import IpmiForm from './IpmiForm';
import ZabbixForm from './ZabbixForm';
import type { MonitorCredentialFormProps } from './types';

export default function MonitorCredentialForm({ protocol, mode }: MonitorCredentialFormProps) {
  if (protocol === 'snmp') return <SnmpForm mode={mode} />;
  if (protocol === 'ipmi') return <IpmiForm mode={mode} />;
  if (protocol === 'zabbix') return <ZabbixForm mode={mode} />;
  return null;
}

export * from './types';
