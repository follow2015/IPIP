import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CloneTab from './CloneTab';

function renderTab() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <CloneTab active onClose={() => {}} />
      </AntApp>
    </QueryClientProvider>
  );
}

describe('CloneTab 冒烟测试', () => {
  it('渲染两步向导标题', () => {
    renderTab();
    expect(screen.getByText('选择模板')).toBeInTheDocument();
    expect(screen.getByText('配置差异项')).toBeInTheDocument();
  });

  it('步骤1 显示模板设备与克隆数量配置', () => {
    renderTab();
    expect(screen.getByText('模板设备')).toBeInTheDocument();
    expect(screen.getByText('克隆数量')).toBeInTheDocument();
  });

  it('步骤1 提供导航按钮', () => {
    renderTab();
    expect(screen.getByRole('button', { name: '下一步' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '上一步' })).toBeNull();
  });

  it('步骤1 含克隆数量输入框', () => {
    renderTab();
    expect(screen.getByRole('spinbutton')).toBeInTheDocument();
  });

  it('未选择模板时下一步按钮禁用', () => {
    renderTab();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
  });
});
