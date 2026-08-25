/**
 * useBatchDeviceCreate — 批量创建设备 + 结果弹窗状态管理
 *
 * 原问题：BatchAddDeviceModal 和 QuickCloneDeviceModal 各自维护一套：
 *   const [resultOpen, setResultOpen] = useState(false);
 *   const [batchResult, setBatchResult] = useState<BatchCreateResult | null>(null);
 *   const handleResultClose = useCallback(() => { ... }, [...]);
 *   const handleRetry = useCallback((failedItems) => { ... }, [...]);
 *
 * 本 Hook 将这套逻辑收拢，并向调用方暴露 submit / retry 语义而非状态细节。
 *
 * 用法：
 *   const batchCreate = useBatchDeviceCreate();
 *
 *   // 提交
 *   await batchCreate.submit(devices);       // 成功后自动打开结果弹窗
 *
 *   // 结果弹窗绑定
 *   <BatchResultModal
 *     open={batchCreate.resultOpen}
 *     result={batchCreate.result}
 *     onClose={batchCreate.closeResult}
 *     onRetry={batchCreate.getRetryRows}     // 获取需要重试的原始行索引集合
 *   />
 */
import { useState, useCallback } from 'react';
import { useBatchCreateDevices } from '@/services/device';
import type { BatchCreateResult, BatchCreateItemResult } from '@/types/models';
import type { CreateDeviceRequest } from '@/services/device';

export function useBatchDeviceCreate() {
  const mutation = useBatchCreateDevices();
  const [result, setResult] = useState<BatchCreateResult | null>(null);
  const [resultOpen, setResultOpen] = useState(false);

  const submit = useCallback(
    async (devices: CreateDeviceRequest[]): Promise<BatchCreateResult | null> => {
      const res = await mutation.mutateAsync(devices); // throws on network error
      const data = res.data ?? null;
      setResult(data);
      if (data) setResultOpen(true);
      return data;
    },
    [mutation],
  );

  const closeResult = useCallback(() => setResultOpen(false), []);

  const getFailedIndices = useCallback(
    (failedItems: BatchCreateItemResult[]): Set<number> =>
      new Set(failedItems.map(item => item.index)),
    [],
  );

  const reset = useCallback(() => {
    setResult(null);
    setResultOpen(false);
  }, []);

  return {
    submit,
    isPending: mutation.isPending,
    result,
    resultOpen,
    closeResult,
    getFailedIndices,
    reset,
  };
}
