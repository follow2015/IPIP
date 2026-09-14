import { get } from '@/services/api-client';

export interface HealthRootData {
  status: string;
  timestamp: string;
  service: string;
  version?: string | null;
}

let cached: Promise<string | null> | null = null;

export function fetchAppVersion(): Promise<string | null> {
  if (!cached) {
    cached = get<HealthRootData>('/health')
      .then((res) => res?.data?.version ?? null)
      .catch(() => {
        cached = null;
        return null;
      });
  }
  return cached;
}
