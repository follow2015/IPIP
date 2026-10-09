import React from 'react';
import type { ScrollXProps } from './types';

const ROOT_STYLE: React.CSSProperties = {
  maxWidth: '100%',
  minWidth: 0,
  overflowX: 'auto'
};

export default function ScrollX({
  children,
  reason,
  className,
  'data-testid': dataTestId
}: ScrollXProps) {
  return (
    <div
      className={className}
      style={ROOT_STYLE}
      data-scrollx-reason={reason}
      data-testid={dataTestId}
    >
      {children}
    </div>
  );
}
