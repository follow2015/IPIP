import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useUnreadCount, useNotificationList, useMarkRead } from './notification';

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('./api-client', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
  del: vi.fn(),
  put: vi.fn()
}));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000, // 同 App.tsx
        retry: false,
        refetchOnWindowFocus: false
      }
    }
  });
  return {
    qc,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
  };
}

function notifItem(id: number, isRead: boolean) {
  return {
    id,
    receipt_id: 1,
    type: 'x',
    severity: 'info' as const,
    title: 't',
    content: null,
    payload: null,
    source_module: null,
    is_read: isRead,
    read_at: null,
    ack_required: false,
    acked_at: null,
    created_at: new Date().toISOString()
  };
}

describe('notification refresh after mark-read', () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    getMock.mockImplementation(async (url: string) => {
      if (String(url).includes('unread-count')) {
        return { data: { unread_count: 2 } };
      }
      return {
        data: {
          items: [notifItem(1, false), notifItem(2, true)],
          total: 2,
          unread_count: 2
        }
      };
    });
    postMock.mockResolvedValue({ data: { marked_count: 1 } });
  });

  it('markRead 后 list 与 unreadCount 都被重新拉取', async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(
      () => {
        const list = useNotificationList({ per_page: 20 }, true);
        const unread = useUnreadCount(true);
        const markRead = useMarkRead();
        return { list, unread, markRead };
      },
      { wrapper }
    );

    await waitFor(() => expect(result.current.list.data).toBeDefined());
    await waitFor(() => expect(result.current.unread.data).toBeDefined());

    const listCallsBefore = getMock.mock.calls.filter(
      (c) => !String(c[0]).includes('unread-count')
    ).length;
    const unreadCallsBefore = getMock.mock.calls.filter((c) =>
      String(c[0]).includes('unread-count')
    ).length;

    act(() => {
      result.current.markRead.mutate([1]);
    });

    await waitFor(
      () => {
        const listCallsAfter = getMock.mock.calls.filter(
          (c) => !String(c[0]).includes('unread-count')
        ).length;
        const unreadCallsAfter = getMock.mock.calls.filter((c) =>
          String(c[0]).includes('unread-count')
        ).length;
        expect(listCallsAfter).toBeGreaterThan(listCallsBefore);
        expect(unreadCallsAfter).toBeGreaterThan(unreadCallsBefore);
      },
      { timeout: 3000 }
    );
  });
});
