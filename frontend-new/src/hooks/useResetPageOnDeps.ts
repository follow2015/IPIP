import { useEffect } from 'react';

export function useResetPageOnDeps(setPage: (page: number) => void, deps: unknown[]): void {
  useEffect(() => {
    setPage(1);
  }, deps);
}
