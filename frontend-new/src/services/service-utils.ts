/**
 * 服务层公共工具（新增文件）
 *
 * 收集各 service 文件中反复出现的模式：
 * 1. unwrapNested  — 解包后端嵌套结构（如 { ports: [...] }、{ storage: [...] }）
 * 2. toSelectOptions — 将列表转换为 Ant Design Select 所需的 { label, value } 格式
 */
import type { ApiResponse } from '@/types/api';


/**
 * 解包形如 `{ [key]: T[] }` 的后端嵌套响应
 *
 * 后端某些端点（如 /devices/<id>/ports、/devices/<id>/storage）
 * 返回的不是直接数组，而是 `{ ports: [...] }` 或 `{ storage: [...] }` 这样
 * 一层包裹结构，导致各 service 文件里重复出现同样的解包逻辑：
 *
 * ```ts
 * // 重构前（重复 N 次）
 * if (res.success && res.data && 'ports' in res.data) {
 *   return { ...res, data: (res.data as DevicePortsResponse).ports };
 * }
 * return res as unknown as typeof res & { data: SomeType[] };
 * ```
 *
 * 使用本函数后：
 * ```ts
 * return unwrapNested(res, 'ports');
 * return unwrapNested(res, 'storage');
 * ```
 */
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


/**
 * 将实体列表转换为 Select 下拉选项
 *
 * ```ts
 * // 重构前（分散在多个文件）
 * return (res.data ?? []).map((r) => ({ label: r.display_name, value: r.id }));
 *
 * // 重构后
 * return toSelectOptions(res.data ?? [], 'display_name', 'id');
 * ```
 */
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
