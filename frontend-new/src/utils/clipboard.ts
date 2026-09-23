/**
 * 剪贴板复制工具
 * - copyToClipboard: 通用复制函数
 * - useCopyInfo: React Hook，返回复制函数 + message 提示
 */
import { useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function formatRecordAsText(record: Record<string, unknown>, labelMap?: Record<string, string>): string {
  return Object.entries(record)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${labelMap?.[k] ?? k}: ${v}`)
    .join('\n');
}

export function useCopyInfo() {
  const { t } = useTranslation();
  return useCallback(
    (text: string, successMsg?: string) => {
      copyToClipboard(text).then((ok) => {
        if (ok) message.success(successMsg ?? t('clipboard.copied'));
        else message.error(t('clipboard.failed'));
      });
    },
    [t]
  );
}
