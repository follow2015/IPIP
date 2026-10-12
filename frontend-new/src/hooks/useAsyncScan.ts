import { useCallback, useEffect, useRef, useState } from 'react';

export const SCAN_TIMEOUT_MS = 5 * 60_000;

export interface UseAsyncScanOptions {
  timeoutMs?: number;
  onExpire?: () => void;
}

export interface UseAsyncScanResult<T> {
  scanningId: T | null;
  beginScan: (id: T) => void;
  endScan: () => void;
}

export function useAsyncScan<T extends number | string | boolean>(
  options: UseAsyncScanOptions = {}
): UseAsyncScanResult<T> {
  const { timeoutMs = SCAN_TIMEOUT_MS, onExpire } = options;

  const [scanningId, setScanningId] = useState<T | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onExpireRef = useRef(onExpire);
  useEffect(() => {
    onExpireRef.current = onExpire;
  }, [onExpire]);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const endScan = useCallback(() => {
    clearTimer();
    setScanningId(null);
  }, [clearTimer]);

  const beginScan = useCallback(
    (id: T) => {
      clearTimer();
      setScanningId(id);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        setScanningId(null);
        onExpireRef.current?.();
      }, timeoutMs);
    },
    [clearTimer, timeoutMs]
  );

  useEffect(() => clearTimer, [clearTimer]);

  return { scanningId, beginScan, endScan };
}
