import { flattenRoutePaths } from '@/router/flattenRoutes';
import { routes } from '@/router/routes';

export type MobileTier = 'A' | 'B' | 'C';

export const MOBILE_TIER_A: readonly string[] = [
  '/login',
  '/dashboard',
  '/monitor/alerts',
  '/monitor/incidents',
  '/monitor/overview',
  '/devices',
  '/devices/:id',
  '/switches/:id',
  '/rooms',
  '/rooms/:id',
  '/cabinets',
  '/cabinets/:id'
] as const;

export const MOBILE_TIER_B: readonly string[] = [
  '/switches',
  '/users',
  '/ip',
  '/topology',
  '/vlans',
  '/network',
  '/link-aggregations',
  '/virtual-rooms',
  '/monitor/history',
  '/monitor/credentials',
  '/monitor/thresholds',
  '/monitor/alert-rules',
  '/customers',
  '/circuits',
  '/carriers',
  '/audit-logs',
  '/login-logs',
  '/device-recycle-bin',
  '/profile',
  '/ai/nlq'
] as const;

export const ROUTE_PATHS: readonly string[] = Array.from(
  new Set(
    flattenRoutePaths(routes)
      .map((p) => (p.startsWith('/') ? p : `/${p}`))
      .filter((p) => p !== '/*')
  )
);

export const MOBILE_TIER_OVERRIDES: Readonly<Record<string, Exclude<MobileTier, 'C'>>> = (() => {
  const map: Record<string, 'A' | 'B'> = {};
  MOBILE_TIER_A.forEach((p) => (map[p] = 'A'));
  MOBILE_TIER_B.forEach((p) => (map[p] = 'B'));
  return map;
})();

export function getMobileTier(path: string): MobileTier {
  return MOBILE_TIER_OVERRIDES[path] ?? 'C';
}
