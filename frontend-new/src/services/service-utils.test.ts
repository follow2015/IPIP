import { describe, it, expect } from 'vitest';
import { unwrapNested, toSelectOptions } from './service-utils';
import type { ApiResponse } from '@/types/api';

function ok<T>(data: T): ApiResponse<T> {
  return { success: true, message: '', data, error_code: null, timestamp: '' };
}

describe('unwrapNested', () => {
  const response = ok({ ports: [1, 2, 3], storage: [] });

  it('解包指定 key 的数组并保持其他字段', () => {
    const result = unwrapNested(response, 'ports');
    expect(result.data).toEqual([1, 2, 3]);
    expect(result.success).toBe(true);
    expect(result.timestamp).toBe('');
  });

  it('key 不存在时降级为原响应（不崩溃）', () => {
    const result = unwrapNested(response, 'unknown' as 'ports');
    expect(result.data).toBe(response.data);
  });

  it('data 为 null 时安全降级', () => {
    const nullResp = ok<{ ports: number[] } | null>(null) as ReturnType<
      typeof ok<{ ports: number[] }>
    >;
    const result = unwrapNested(nullResp, 'ports');
    expect(result.data).toBeNull();
  });
});

describe('toSelectOptions', () => {
  it('将实体列表映射为 { label, value }', () => {
    const items = [
      { id: 1, name: 'Alpha' },
      { id: 2, name: 'Beta' }
    ];
    expect(toSelectOptions(items, 'name', 'id')).toEqual([
      { label: 'Alpha', value: 1 },
      { label: 'Beta', value: 2 }
    ]);
  });

  it('空列表返回空数组', () => {
    expect(toSelectOptions([], 'name', 'id')).toEqual([]);
  });

  it('label 非字符串时自动 String 化', () => {
    const items = [{ id: 1, code: 42 }];
    expect(toSelectOptions(items, 'code', 'id')).toEqual([{ label: '42', value: 1 }]);
  });

  it('支持自定义 label / value 字段', () => {
    const items = [{ device_id: 'D1', display_name: 'Core' }];
    expect(toSelectOptions(items, 'display_name', 'device_id')).toEqual([
      { label: 'Core', value: 'D1' }
    ]);
  });
});
