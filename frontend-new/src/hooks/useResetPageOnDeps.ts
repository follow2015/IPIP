import { useEffect } from 'react';

export function useResetPageOnDeps(setPage: (page: number) => void, deps: unknown[]): void {
  useEffect(() => {
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
