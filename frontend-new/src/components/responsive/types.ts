
export type OverflowStrategy = 'scroll' | 'wrap' | 'clip';

export interface OverflowPolicy {
  strategy: OverflowStrategy;
  reason: string;
}

export interface ScrollXProps {
  children: React.ReactNode;
  reason: string;
  className?: string;
  'data-testid'?: string;
}

export type NarrowFallback = 'tabs' | 'block' | 'vertical';

export interface SegmentedOption {
  label: React.ReactNode;
  value: string | number;
}

export interface SegmentedResponsiveProps {
  isMobile: boolean;
  options: SegmentedOption[];
  value: string | number;
  onChange: (value: string | number) => void;
  reason: string;
  narrowFallback?: NarrowFallback;
  className?: string;
}
