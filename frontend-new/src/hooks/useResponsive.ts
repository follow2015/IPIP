import { Grid } from 'antd';

const { useBreakpoint } = Grid;

export type Breakpoint = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl';

export const RESPONSIVE_BREAKPOINTS: Record<Breakpoint, number> = {
  xs: 576,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1600
};

function getFallbackScreens(): Partial<Record<Breakpoint, boolean>> {
  const w = (globalThis as { innerWidth?: number }).innerWidth;
  if (w === undefined) return {};
  return {
    xs: w < RESPONSIVE_BREAKPOINTS.xs,
    sm: w >= RESPONSIVE_BREAKPOINTS.sm,
    md: w >= RESPONSIVE_BREAKPOINTS.md,
    lg: w >= RESPONSIVE_BREAKPOINTS.lg,
    xl: w >= RESPONSIVE_BREAKPOINTS.xl,
    xxl: w >= RESPONSIVE_BREAKPOINTS.xxl
  };
}

export interface ResponsiveState {
  screens: Partial<Record<Breakpoint, boolean>>;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isNarrow: boolean;
}

export function useResponsive(): ResponsiveState {
  const screens = useBreakpoint();
  const resolved: Partial<Record<Breakpoint, boolean>> =
    Object.keys(screens).length === 0 ? getFallbackScreens() : screens;

  const isMobile = !resolved.md;
  const isDesktop = !!resolved.lg;

  return {
    screens: resolved,
    isMobile,
    isTablet: !!resolved.md && !resolved.lg,
    isDesktop,
    isNarrow: !resolved.sm
  };
}
