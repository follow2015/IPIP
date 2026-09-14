import { useCallback } from 'react';
import { App } from 'antd';

type HookModal = ReturnType<typeof App.useApp>['modal'];

export type ConfirmFn = HookModal['confirm'];

export type ConfirmOptions = Parameters<ConfirmFn>[0];

const CONFIRM_DEFAULTS = {
  okText: '确定',
  cancelText: '取消',
  centered: true,
  mask: { closable: false }
} as const;

export function useConfirm(): ConfirmFn {
  const { modal } = App.useApp();

  return useCallback(
    (options: ConfirmOptions) => modal.confirm({ ...CONFIRM_DEFAULTS, ...options }),
    [modal]
  );
}
