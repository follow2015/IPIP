import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BatchActionBar } from '@/components/BatchActionBar';

describe('BatchActionBar', () => {
  it('count=0 时不渲染', () => {
    const { container } = render(<BatchActionBar count={0} onClear={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('显示已选计数与单位', () => {
    render(<BatchActionBar count={3} unit="台设备" onClear={() => {}} />);
    expect(screen.getByText(/已选择/)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/台设备/)).toBeInTheDocument();
  });

  it('点击取消选择触发 onClear', () => {
    const onClear = vi.fn();
    render(
      <BatchActionBar count={2} onClear={onClear}>
        action
      </BatchActionBar>
    );
    fireEvent.click(screen.getByText('取消选择'));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('渲染 children 操作插槽', () => {
    render(
      <BatchActionBar count={1} onClear={() => {}}>
        <button>批量删除</button>
      </BatchActionBar>
    );
    expect(screen.getByText('批量删除')).toBeInTheDocument();
  });
});
