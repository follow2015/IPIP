import { useEffect } from 'react';

export const LARGE_UNPAGED_THRESHOLD = 100;

export function useLargeUnpagedListWarning(rowCount: number, isUnpaged: boolean): void {
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    if (!isUnpaged || rowCount <= LARGE_UNPAGED_THRESHOLD) return;
    console.warn(
      `[DataTable] rendering ${rowCount} rows with pagination disabled ` +
        `(threshold ${LARGE_UNPAGED_THRESHOLD}). Prefer server-side pagination, ` +
        'or enable virtual + a fixed scroll.y when rendering everything at once is intended.'
    );
  }, [rowCount, isUnpaged]);
}
