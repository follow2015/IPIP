import React, { useMemo } from 'react';
import { Segmented, Tabs } from 'antd';
import type { SegmentedResponsiveProps } from './types';

export default function SegmentedResponsive({
  isMobile,
  options,
  value,
  onChange,
  narrowFallback = 'tabs',
  className
}: SegmentedResponsiveProps) {
  const keyOf = (v: string | number) => String(v);
  const valueByKey = useMemo(() => {
    const map = new Map<string, string | number>();
    options.forEach((o) => map.set(keyOf(o.value), o.value));
    return map;
  }, [options]);

  if (!isMobile) {
    return <Segmented className={className} options={options} value={value} onChange={onChange} />;
  }

  if (narrowFallback === 'block') {
    return (
      <Segmented className={className} block options={options} value={value} onChange={onChange} />
    );
  }

  if (narrowFallback === 'vertical') {
    return (
      <Segmented
        className={className}
        vertical
        options={options}
        value={value}
        onChange={onChange}
      />
    );
  }

  return (
    <Tabs
      className={className}
      activeKey={keyOf(value)}
      onChange={(key) => {
        const original = valueByKey.get(key);
        if (original !== undefined) onChange(original);
      }}
      items={options.map((o) => ({ key: keyOf(o.value), label: o.label }))}
    />
  );
}
