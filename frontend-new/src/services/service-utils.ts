/**
 * 服务层公共工具（新增文件）
 *
 * 收集各 service 文件中反复出现的模式：
 * 1. unwrapNested  — 解包后端嵌套结构（如 { ports: [...] }、{ storage: [...] }）
 * 2. toSelectOptions — 将列表转换为 Ant Design Select 所需的 { label, value } 格式
 */
import type { ApiResponse } from '@/types/api';


export function unwrapNested<W extends object, K extends keyof W>(
  response: ApiResponse<W>,
  key: K,
): ApiResponse<W[K]> {
  const data = response.data;
  if (data && typeof data === 'object' && key in data) {
    return { ...response, data: data[key] };
  }
  
  return response as unknown as ApiResponse<W[K]>;
}


export function toSelectOptions<T extends object>(
  items: T[],
  labelKey: keyof T,
  valueKey: keyof T,
): Array<{ label: string; value: T[keyof T] }> {
  return items.map((item) => ({
    label: String(item[labelKey]),
    value: item[valueKey],
  }));
}
