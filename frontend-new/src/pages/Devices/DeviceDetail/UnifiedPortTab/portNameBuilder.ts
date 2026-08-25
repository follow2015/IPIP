/**
 * 批量端口名生成（原 batchPreview / handleBatchAdd 中的重复逻辑统一收敛）
 *
 * 命名规则：前缀 + 槽位/卡号/端口号
 * - 模板端口：前缀取自 PORT_TYPE_TEMPLATES（如 GE → GE）
 * - 自定义端口：前缀取自 custom_prefix
 */
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';

export interface PortNameSpec {
  port_name: string;
  port_type: string;
  speed: string;
  usage_status: string;
}

export interface PortGroupInput {
  template?: string;
  slot?: number;
  card?: number;
  start_port?: number;
  end_port?: number;
  custom_prefix?: string;
  custom_type?: string;
  custom_speed?: string;
  usage_status?: string;
}


export function expandPortGroups(groups: PortGroupInput[] | undefined): PortNameSpec[] {
  if (!groups) return [];
  const result: PortNameSpec[] = [];
  for (const group of groups) {
    const {
      template,
      slot,
      card,
      start_port,
      end_port,
      custom_prefix,
      custom_type,
      custom_speed,
      usage_status
    } = group ?? {};
    if (!template || !start_port || !end_port || start_port > end_port) continue;
    const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
    const prefix = template === 'custom' ? (custom_prefix ?? '') : (tpl?.prefix ?? '');
    if (!prefix) continue;
    const speed = template === 'custom' ? (custom_speed ?? '') : (tpl?.speed ?? '');
    const portType = template === 'custom' ? (custom_type ?? '') : (tpl?.value ?? '');
    const s = slot ?? 0;
    const c = card ?? 0;
    const status = usage_status ?? 'free';
    for (let i = start_port; i <= end_port; i++) {
      result.push({
        port_name: `${prefix}${s}/${c}/${i}`,
        port_type: portType,
        speed,
        usage_status: status
      });
    }
  }
  return result;
}


export function previewPortNames(groups: PortGroupInput[] | undefined, limit = 500): string[] {
  return expandPortGroups(groups)
    .slice(0, limit)
    .map((p) => p.port_name);
}
