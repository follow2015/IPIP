import type { QueryClient, QueryKey } from '@tanstack/react-query';

export const DEFAULT_COALESCE_DELAY_MS = 300;

export interface CoalescedInvalidator {
  invalidate(queryKey: QueryKey): void;
  flush(): void;
  readonly pendingCount: number;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value ?? null);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  const obj = value as Record<string, unknown>;
  const entries = Object.keys(obj)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`);
  return `{${entries.join(',')}}`;
}

function keyToString(queryKey: QueryKey): string {
  try {
    return stableStringify(queryKey);
  } catch {
    return String(queryKey);
  }
}

export function createCoalescedInvalidator(
  queryClient: QueryClient,
  delayMs: number = DEFAULT_COALESCE_DELAY_MS
): CoalescedInvalidator {
  const pending = new Map<string, QueryKey>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    if (pending.size === 0) return;
    const keys = [...pending.values()];
    pending.clear();
    for (const queryKey of keys) {
      queryClient.invalidateQueries({ queryKey });
    }
  };

  return {
    invalidate(queryKey) {
      pending.set(keyToString(queryKey), queryKey);
      if (timer === null) {
        timer = setTimeout(flush, delayMs);
      }
    },
    flush,
    get pendingCount() {
      return pending.size;
    }
  };
}
