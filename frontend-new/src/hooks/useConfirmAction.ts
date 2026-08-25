import { useCallback } from 'react';
import type { ReactNode } from 'react';
import { confirm } from '@/utils/confirm';
import { useMessage } from '@/hooks/useMessage';


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
            message.error(opts.errorMessage ?? (err instanceof Error ? err.message : '操作失败'));
          }
        }
      });
    },
    [message]
  );
}
