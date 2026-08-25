import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import StatusTag from './StatusTag';
import { PORT_USAGE_STATUS_MAP, CONNECTION_STATUS_MAP } from '@/types/enums';

describe('StatusTag', () => {
  it('按映射渲染 label 与 color', () => {
    const { container } = render(<StatusTag status="active" statusMap={CONNECTION_STATUS_MAP} />);
    const tag = container.querySelector('.ant-tag')!;
    expect(tag).toHaveTextContent('活跃');
    expect(tag.className).toContain('ant-tag-green');
  });

  it('回归护栏(R1)：端口占用状态规范色——free=绿、occupied=蓝（消除 NicTab/ConnectionTab 颜色相反）', () => {
    const { container: freeBox } = render(
      <StatusTag status="free" statusMap={PORT_USAGE_STATUS_MAP} />
    );
    const { container: occBox } = render(
      <StatusTag status="occupied" statusMap={PORT_USAGE_STATUS_MAP} />
    );
    expect(freeBox.querySelector('.ant-tag')!.className).toContain('ant-tag-green');
    expect(occBox.querySelector('.ant-tag')!.className).toContain('ant-tag-blue');
  });

  it('未命中映射时回退显示原值', () => {
    const { container } = render(<StatusTag status="weird" statusMap={CONNECTION_STATUS_MAP} />);
    expect(container.querySelector('.ant-tag')).toHaveTextContent('weird');
  });

  it('null/undefined 状态显示 -', () => {
    const { container: nullCase } = render(
      <StatusTag status={null} statusMap={PORT_USAGE_STATUS_MAP} />
    );
    const { container: undefCase } = render(
      <StatusTag status={undefined} statusMap={PORT_USAGE_STATUS_MAP} />
    );
    expect(nullCase.querySelector('.ant-tag')).toHaveTextContent('-');
    expect(undefCase.querySelector('.ant-tag')).toHaveTextContent('-');
  });
});
