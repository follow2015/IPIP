import { isValidElement, type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

interface ElementLike {
  type?: unknown;
  props?: { children?: ReactNode };
}

export function isRedirect(node: ReactNode): boolean {
  if (Array.isArray(node)) return node.some(isRedirect);
  if (!isValidElement(node)) return false;
  const el = node as unknown as ElementLike;
  if (el.type === Navigate) return true;
  return isRedirect(el.props?.children);
}

export function flattenRoutes(
  routes: RouteObject[],
  prefix = ''
): { path: string; element: ReactNode }[] {
  const out: { path: string; element: ReactNode }[] = [];
  const walk = (list: RouteObject[], base: string) => {
    list.forEach((route) => {
      const path = route.path ?? '';
      const full = route.index ? base || '/' : base + path;
      if (route.element !== undefined) out.push({ path: full, element: route.element });
      if (route.children) walk(route.children as RouteObject[], base + path.replace(/\/$/, ''));
    });
  };
  walk(routes, prefix);
  return out;
}

export function flattenRoutePaths(routes: RouteObject[]): string[] {
  return flattenRoutes(routes)
    .filter((r) => !isRedirect(r.element))
    .map((r) => r.path);
}
