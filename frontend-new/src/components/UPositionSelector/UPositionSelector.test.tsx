import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UPositionSelector from '@/components/UPositionSelector/UPositionSelector';
import type { OccupiedPosition } from '@/components/UPositionSelector/UPositionSelector';

const sampleDevices: OccupiedPosition[] = [
  {
    uPosition: 1,
    uSize: 2,
    deviceId: 1,
    deviceName: 'Server-A',
    deviceType: 'server',
    ip: '10.0.0.1',
    power: 500
  },
  { uPosition: 10, uSize: 1, deviceId: 2, deviceName: 'Switch-B', deviceType: 'switch' }
];

function renderRack(props: Partial<React.ComponentProps<typeof UPositionSelector>> = {}) {
  return render(
    <MemoryRouter>
      <UPositionSelector occupiedPositions={sampleDevices} {...props} />
    </MemoryRouter>
  );
}

describe('UPositionSelector 冒烟', () => {
  it('渲染机柜头与设备块', () => {
    renderRack();
    expect(screen.getByText('U 位布局')).toBeInTheDocument();
    expect(screen.getByText('Server-A')).toBeInTheDocument();
    expect(screen.getByText('Switch-B')).toBeInTheDocument();
    expect(screen.getByText(/2 台/)).toBeInTheDocument();
  });

  it('readOnly 模式不显示"可拖拽"', () => {
    const { container } = renderRack({ readOnly: true });
    expect(within(container).queryByText(/可拖拽/)).toBeNull();
  });

  it('非 readOnly 模式显示"可拖拽"', () => {
    const { container } = renderRack({ readOnly: false });
    expect(within(container).getByText(/可拖拽/)).toBeInTheDocument();
  });

  it('点击设备块弹出详情面板', () => {
    renderRack();
    expect(screen.getByText('点击设备查看详情')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Server-A'));
    expect(screen.getByText('查看设备详情')).toBeInTheDocument();
    expect(screen.queryByText('点击设备查看详情')).toBeNull();
  });

  it('点击设备触发 onSelect 回调', () => {
    const onSelect = vi.fn();
    renderRack({ onSelect });
    fireEvent.click(screen.getByText('Switch-B'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]?.deviceName).toBe('Switch-B');
  });

  it('拖拽落点触发 onPositionChange（模拟 drop 事件）', () => {
    const onPositionChange = vi.fn();
    renderRack({ onPositionChange });
    const body = screen.getByText('U 位布局').parentElement!.parentElement!;
    const rackBody = body.querySelector('[style*="position: relative"]') as HTMLElement;
    expect(rackBody).toBeTruthy();
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' };
    fireEvent.dragStart(screen.getByText('Server-A'), { dataTransfer });
    fireEvent.drop(rackBody);
    expect(onPositionChange).toHaveBeenCalled();
  });
});
