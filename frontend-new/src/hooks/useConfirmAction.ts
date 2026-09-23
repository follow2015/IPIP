import { useCallback } from 'react';
import type { ReactNode } from 'react';
import { useConfirm } from '@/utils/confirm';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

export interface ConfirmActionOptions {
  title: ReactNode;
  content: ReactNode;
  okType?: 'primary' | 'danger' | 'default';
  icon?: ReactNode;
  successMessage?: ReactNode;
  errorMessage?: ReactNode;
  onConfirm: () => Promise<unknown> | void;
  afterConfirm?: () => void;
}

export function useConfirmAction() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const message = useMessage();
  return useCallback(
    (opts: ConfirmActionOptions) => {
      confirm({
        title: opts.title,
        content: opts.content,
        icon: opts.icon,
        okType: opts.okType ?? 'danger',
        onOk: async () => {
          try {
            await opts.onConfirm();
            if (opts.successMessage !== undefined) message.success(opts.successMessage);
            opts.afterConfirm?.();
          } catch (err) {
            message.error(
              opts.errorMessage ?? (err instanceof Error ? err.message : t('message.operationFailed'))
            );
          }
        }
      });
    },
    [confirm, message, t]
  );
}
