import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import * as api from './api-client';
import {
  useCreateConnection,
  useDisconnectPortLink,
  useUpdateConnection
} from './device-connection';
import { queryKeys } from './query-keys';
import type { ConnectionRequest } from './device-connection';

vi.mock('./api-client', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn()
}));

function setup() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, spy, wrapper };
}

const mockPost = (data: unknown) =>
  (api.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data });
const mockPut = (data: unknown) =>
  (api.put as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data });
const mockDel = (data: unknown) =>
  (api.del as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data });

describe('device-connection mutations（C1 迁移至 useInvalidatingMutation）', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateConnection 带对端 switch_device_id → 失效本机+对端三组 key', async () => {
    mockPost({ id: 1 });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCreateConnection(1), { wrapper });
    act(() => result.current.mutate({ switch_device_id: 2, connection_type: 'D2N' }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(api.post).toHaveBeenCalled();
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.connections(1) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...queryKeys.devices.detail(1), 'port-links'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.networkPorts(1) });
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.connections(2) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...queryKeys.devices.detail(2), 'port-links'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.networkPorts(2) });
  });

  it('useCreateConnection 无对端 → 仅失效本机三组 key', async () => {
    mockPost({ id: 1 });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCreateConnection(1), { wrapper });
    act(() =>
      result.current.mutate({ connection_type: 'D2N' } as Omit<ConnectionRequest, 'device_id'>)
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.connections(1) });
    expect(spy).not.toHaveBeenCalledWith({ queryKey: queryKeys.devices.connections(2) });
  });

  it('useDisconnectPortLink 响应含 peer_device_id → 失效对端 port-links/networkPorts', async () => {
    mockDel({ peer_device_id: 7 });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useDisconnectPortLink(3), { wrapper });
    act(() => result.current.mutate(55));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(api.del).toHaveBeenCalled();
    expect(spy).toHaveBeenCalledWith({ queryKey: [...queryKeys.devices.detail(3), 'port-links'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.networkPorts(3) });
    expect(spy).toHaveBeenCalledWith({ queryKey: [...queryKeys.devices.detail(7), 'port-links'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.networkPorts(7) });
  });

  it('useUpdateConnection → 失效 devices.all', async () => {
    mockPut({ id: 1 });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useUpdateConnection(), { wrapper });
    act(() => result.current.mutate({ connId: 1, data: {} }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.all });
  });
});
