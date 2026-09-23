import { useCallback } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';

type HookModal = ReturnType<typeof App.useApp>['modal'];

export type ConfirmFn = HookModal['confirm'];

export type ConfirmOptions = Parameters<ConfirmFn>[0];

const CONFIRM_DEFAULTS = {
  centered: true,
  mask: { closable: false }
} as const;

export function useConfirm(): ConfirmFn {
  const { modal } = App.useApp();
  const { t } = useTranslation();

  return useCallback(
    (options: ConfirmOptions) =>
      modal.confirm({
        ...CONFIRM_DEFAULTS,
        okText: t('action.ok'),
        cancelText: t('action.cancel'),
        ...options
      }),
    [modal, t]
  );
}
