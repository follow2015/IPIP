import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useConfirmAction } from './useConfirmAction';
import { confirm } from '@/utils/confirm';
import { useMessage } from '@/hooks/useMessage';

const mockMessage = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn()
};

vi.mock('@/utils/confirm', () => ({ confirm: vi.fn() }));
vi.mock('@/hooks/useMessage', () => ({ useMessage: () => mockMessage }));

function getLastConfirm() {
  const calls = vi.mocked(confirm).mock.calls;
  return calls[calls.length - 1][0];
}

describe('useConfirmAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('调用 confirm 并透传 title/content/okType(默认 danger)', () => {
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', onConfirm: vi.fn() });
    });
    const call = getLastConfirm();
    expect(call.title).toBe('T');
    expect(call.content).toBe('C');
    expect(call.okType).toBe('danger');
  });

  it('okType 可覆盖为 primary', () => {
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', okType: 'primary', onConfirm: vi.fn() });
    });
    expect(getLastConfirm().okType).toBe('primary');
  });

  it('onOk 成功: 执行 onConfirm + success 提示 + afterConfirm', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const afterConfirm = vi.fn();
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', successMessage: 'ok', onConfirm, afterConfirm });
    });
    await act(async () => {
      await getLastConfirm().onOk!();
    });
    expect(onConfirm).toHaveBeenCalled();
    expect(mockMessage.success).toHaveBeenCalledWith('ok');
    expect(afterConfirm).toHaveBeenCalled();
  });

  it('onOk 失败: 用 errorMessage 提示', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', errorMessage: '失败', onConfirm });
    });
    await act(async () => {
      await getLastConfirm().onOk!();
    });
    expect(mockMessage.error).toHaveBeenCalledWith('失败');
  });

  it('onOk 失败: 回退到错误原始 message', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('原始错误'));
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', onConfirm });
    });
    await act(async () => {
      await getLastConfirm().onOk!();
    });
    expect(mockMessage.error).toHaveBeenCalledWith('原始错误');
  });

  it('无 successMessage 时不弹成功提示', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useConfirmAction());
    act(() => {
      result.current({ title: 'T', content: 'C', onConfirm });
    });
    await act(async () => {
      await getLastConfirm().onOk!();
    });
    expect(mockMessage.success).not.toHaveBeenCalled();
  });
});
