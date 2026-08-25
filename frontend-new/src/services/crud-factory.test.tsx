import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createCrudHooks } from './crud-factory';

const { getMock, postMock, putMock, delMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
  delMock: vi.fn()
}));

vi.mock('./api-client', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
  put: (...args: unknown[]) => putMock(...args),
  del: (...args: unknown[]) => delMock(...args)
}));

interface Thing {
  id: number;
  name: string;
}
type CreateThing = { name: string };
type UpdateThing = { id: number; name: string };

function ok<T>(data: T) {
  return { success: true, message: '', data, error_code: null, timestamp: '' };
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  putMock.mockReset();
  delMock.mockReset();
});

describe('createCrudHooks', () => {
  const hooks = createCrudHooks<Thing, CreateThing, UpdateThing>({
    basePath: '/things',
    queryKey: ['things']
  });

  it('useList 以 basePath 调 get 并返回分页数据', async () => {
    getMock.mockResolvedValue(
      ok({ items: [{ id: 1, name: 'A' }], total: 1, page: 1, page_size: 10 })
    );
    const wrapper = makeWrapper();
    const { result } = renderHook(() => hooks.useList(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getMock).toHaveBeenCalledWith('/things', undefined);
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].name).toBe('A');
  });

  it('useCreate 以 createPath 调 post 并在成功后失效缓存', async () => {
    postMock.mockResolvedValue(ok({ id: 1, name: 'New' }));
    const wrapper = makeWrapper();
    const { result } = renderHook(() => hooks.useCreate(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ name: 'New' });
    });
    expect(postMock).toHaveBeenCalledWith('/things', { name: 'New' });
  });

  it('useUpdate 剥离 id 并以 basePath/:id 调 put', async () => {
    putMock.mockResolvedValue(ok({ id: 7, name: 'X' }));
    const wrapper = makeWrapper();
    const { result } = renderHook(() => hooks.useUpdate(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ id: 7, name: 'X' });
    });
    expect(putMock).toHaveBeenCalledWith('/things/7', { name: 'X' });
  });

  it('useDelete 以 basePath/:id 调 del', async () => {
    delMock.mockResolvedValue(ok(undefined));
    const wrapper = makeWrapper();
    const { result } = renderHook(() => hooks.useDelete(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(9);
    });
    expect(delMock).toHaveBeenCalledWith('/things/9');
  });

  it('useOptions 默认走 basePath/all 并映射为下拉选项', async () => {
    getMock.mockResolvedValue(
      ok([
        { id: 1, name: 'A' },
        { id: 2, name: 'B' }
      ])
    );
    const wrapper = makeWrapper();
    const { result } = renderHook(() => hooks.useOptions(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getMock).toHaveBeenCalledWith('/things/all');
    expect(result.current.data).toEqual([
      { label: 'A', value: 1 },
      { label: 'B', value: 2 }
    ]);
  });

  it('useOptions 支持自定义 label/value 字段', async () => {
    getMock.mockResolvedValue(ok([{ id: 1, display_name: 'Core' }]));
    const customHooks = createCrudHooks<
      { id: number; display_name: string },
      { display_name: string },
      { id: number; display_name: string }
    >({
      basePath: '/devices',
      queryKey: ['devices'],
      optionsConfig: { labelKey: 'display_name', valueKey: 'id' }
    });
    const wrapper = makeWrapper();
    const { result } = renderHook(() => customHooks.useOptions(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getMock).toHaveBeenCalledWith('/devices/all');
    expect(result.current.data).toEqual([{ label: 'Core', value: 1 }]);
  });
});
