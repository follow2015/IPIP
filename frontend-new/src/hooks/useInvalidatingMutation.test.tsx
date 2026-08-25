import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useInvalidatingMutation } from './useInvalidatingMutation';

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return {
    qc,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
  };
}

describe('useInvalidatingMutation（扩展后）', () => {
  beforeEach(() => vi.clearAllMocks());

  it('静态 key：mutation 成功后失效指定 key（向后兼容）', async () => {
    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useInvalidatingMutation((v: number) => Promise.resolve(v), ['devices', 1, 'connections']),
      { wrapper }
    );
    act(() => result.current.mutate(1));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
  });

  it('动态 key：根据 variables 失效多个 key（含对端）', async () => {
    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useInvalidatingMutation(
          (v: { id: number; peer: number }) => Promise.resolve(v),
          (_data, v: { id: number; peer: number }) => [
            ['devices', v.id, 'connections'],
            ['devices', v.peer, 'connections']
          ]
        ),
      { wrapper }
    );
    act(() => result.current.mutate({ id: 1, peer: 2 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 2, 'connections'] });
  });

  it('动态 key：基于响应 data 计算对端 key（res.data.peer_device_id）', async () => {
    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useInvalidatingMutation(
          () => Promise.resolve({ data: { peer_device_id: 9 } }),
          (res: { data: { peer_device_id: number } }) => {
            const keys: Array<readonly unknown[]> = [['devices', 1, 'port-links']];
            if (res.data?.peer_device_id) {
              keys.push(['devices', res.data.peer_device_id, 'port-links']);
            }
            return keys;
          }
        ),
      { wrapper }
    );
    act(() => result.current.mutate(undefined));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'port-links'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 9, 'port-links'] });
  });

  it('调用方 onSuccess 与自动失效合并执行（不被覆盖）', async () => {
    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const caller = vi.fn();
    const { result } = renderHook(
      () =>
        useInvalidatingMutation((v: number) => Promise.resolve(v), ['devices', 1, 'connections'], {
          onSuccess: (d: number) => caller(d)
        }),
      { wrapper }
    );
    act(() => result.current.mutate(42));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
    expect(caller).toHaveBeenCalledWith(42);
  });
});
