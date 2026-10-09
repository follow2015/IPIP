import { useCallback } from 'react';
import type { FormInstance } from 'antd';
import { useTranslation } from 'react-i18next';
import { useConfirm } from '@/utils/confirm';

export interface UseDirtyGuardOptions {
  form?: FormInstance;
  isPending?: boolean;
  isDirty?: boolean;
}

export interface UseDirtyGuardReturn {
  requestClose: (onClose: () => void) => void;
}

export function useDirtyGuard(options: UseDirtyGuardOptions): UseDirtyGuardReturn {
  const { form, isPending = false, isDirty } = options;
  const { t } = useTranslation('common');
  const confirm = useConfirm();

  const requestClose = useCallback(
    (onClose: () => void) => {
      if (isPending) return;

      const dirty = isDirty ?? form?.isFieldsTouched() ?? false;
      if (!dirty) {
        onClose();
        return;
      }

      confirm({
        title: t('confirm.unsavedTitle'),
        content: t('confirm.unsavedContent'),
        okText: t('action.discard'),
        cancelText: t('action.cancel'),
        okButtonProps: { danger: true },
        onOk: onClose
      });
    },
    [confirm, form, isDirty, isPending, t]
  );

  return { requestClose };
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).sort().join(',')}]`;
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj)
      .sort()
      .map((k) => `${k}:${stableStringify(obj[k])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value ?? null);
}

export function useSnapshotDirty(initial: unknown, current: unknown): boolean {
  return stableStringify(initial) !== stableStringify(current);
}
