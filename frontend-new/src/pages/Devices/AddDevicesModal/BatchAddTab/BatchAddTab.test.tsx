import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BatchAddTab from './BatchAddTab';

function renderTab() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <BatchAddTab active onClose={() => {}} />
      </AntApp>
    </QueryClientProvider>
  );
}

describe('BatchAddTab 冒烟', () => {
  it('渲染公共字段 + 表格（active 时预置 3 行）', () => {
    renderTab();
    expect(screen.getByText('设备主类型')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /批量创建/ })).toBeInTheDocument();
    expect(screen.getByText('共 3 行')).toBeInTheDocument();
  });

  it('未选设备主类型时提示', () => {
    renderTab();
    expect(screen.getByText('请先选择设备主类型')).toBeInTheDocument();
  });

  it('点击「添加行」增加行数', () => {
    renderTab();
    fireEvent.click(screen.getByText('添加行'));
    expect(screen.getByText('共 4 行')).toBeInTheDocument();
  });

  it('提交按钮初始禁用（未选主类型）', () => {
    renderTab();
    const btn = screen.getByRole('button', { name: /批量创建/ });
    expect(btn).toBeDisabled();
  });

  it('非节点模式下渲染 U 位工具栏（自动分配/重生成名称）', () => {
    renderTab();
    expect(screen.getByText('自动分配U位')).toBeInTheDocument();
    expect(screen.getByText('重生成名称')).toBeInTheDocument();
  });
});
