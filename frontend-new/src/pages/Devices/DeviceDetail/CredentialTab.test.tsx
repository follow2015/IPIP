import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';

const hoisted = vi.hoisted(() => ({
  statusData: { configured_protocols: ['snmp'] as string[] },
  creds: [{ id: 2, name: '机房A', protocol: 'ipmi', linked_count: 1 }] as Record<string, unknown>[],
  groups: [] as Record<string, unknown>[],
  linkExistingStub: vi.fn().mockResolvedValue({ success: true }),
  createLinkStub: vi.fn().mockResolvedValue({ success: true }),
  unlinkStub: vi.fn().mockResolvedValue({ success: true }),
  updateDeviceStub: vi.fn().mockResolvedValue({ success: true })
}));

vi.mock('@/services/monitor', () => ({
  useDeviceMonitorStatus: () => ({ data: hoisted.statusData }),
  useMonitorCredentials: () => ({ data: hoisted.creds, isLoading: false }),
  useCreateAndLinkCredential: () => ({ mutateAsync: hoisted.createLinkStub, isPending: false }),
  useLinkExistingCredential: () => ({ mutateAsync: hoisted.linkExistingStub, isPending: false }),
  useUnlinkCredential: () => ({ mutateAsync: hoisted.unlinkStub, isPending: false }),
  useUpdateCredentialPayload: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useToggleDeviceMonitor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useMetricTemplateGroups: () => ({ data: hoisted.groups, isLoading: false })
}));

vi.mock('@/services/device', () => ({
  useUpdateDevice: () => ({ mutateAsync: hoisted.updateDeviceStub, isPending: false })
}));

const messageError = vi.fn();
const messageSuccess = vi.fn();
const messageWarning = vi.fn();
vi.mock('@/hooks/useMessage', () => ({
  useMessage: () => ({ error: messageError, success: messageSuccess, warning: messageWarning })
}));

import CredentialTab from './CredentialTab';

const deviceFixture = {
  id: 1,
  device_type: 'server',
  brand: null,
  metric_template_group_id: null
} as unknown as import('@/types/models').Device;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AntApp>{children}</AntApp>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  hoisted.statusData = { configured_protocols: ['snmp'] };
  hoisted.creds = [{ id: 2, name: '机房A', protocol: 'ipmi', linked_count: 1 }];
  hoisted.groups = [];
  hoisted.linkExistingStub.mockClear();
  hoisted.createLinkStub.mockClear();
  hoisted.unlinkStub.mockClear();
  hoisted.updateDeviceStub.mockClear();
  messageError.mockClear();
  messageSuccess.mockClear();
  messageWarning.mockClear();
});

describe('CredentialTab', () => {
  it('渲染三段标题', () => {
    render(<CredentialTab device={deviceFixture} />, { wrapper: makeWrapper() });
    expect(screen.getByText('本机已关联凭据')).toBeInTheDocument();
    expect(screen.getByText('关联已有共享凭据')).toBeInTheDocument();
    expect(screen.getByText('新建共享凭据并关联本机')).toBeInTheDocument();
  });

  it('本机已关联凭据可取消关联', async () => {
    const user = userEvent.setup();
    render(<CredentialTab device={deviceFixture} />, { wrapper: makeWrapper() });
    await user.click(screen.getByText('取消关联'));
    await waitFor(() =>
      expect(hoisted.unlinkStub).toHaveBeenCalledWith({ deviceId: 1, protocol: 'snmp' })
    );
  });

  it.skip('关联本机触发 linkExisting', async () => {
    const user = userEvent.setup();
    render(<CredentialTab device={deviceFixture} />, { wrapper: makeWrapper() });
    const candSelect = screen.getAllByRole('combobox')[2].closest('.ant-select-selector');
    fireEvent.mouseDown(candSelect as HTMLElement);
    await user.click(await screen.findByText(/机房A（已关联 1 台）/));
    await user.click(screen.getByText('关联本机'));
    await waitFor(() =>
      expect(hoisted.linkExistingStub).toHaveBeenCalledWith({
        credentialId: 2,
        device_ids: [1]
      })
    );
  });

  it('必填字段未填不触发 createLink', async () => {
    const user = userEvent.setup();
    render(<CredentialTab device={deviceFixture} />, { wrapper: makeWrapper() });
    await user.click(screen.getByText('新建并关联'));
    await waitFor(() => expect(screen.getByText('请输入凭据名称')).toBeInTheDocument());
    expect(hoisted.createLinkStub).not.toHaveBeenCalled();
  });

  it('填写 SNMP 凭据后触发 createLink', async () => {
    const user = userEvent.setup();
    render(<CredentialTab device={deviceFixture} />, { wrapper: makeWrapper() });
    await user.type(screen.getByPlaceholderText(/如：机房A SNMP只读团体字/), '机房A');
    await user.type(screen.getByLabelText('Community'), 'public');
    await user.click(screen.getByText('新建并关联'));
    await waitFor(() =>
      expect(hoisted.createLinkStub).toHaveBeenCalledWith(
        expect.objectContaining({
          protocol: 'snmp',
          payload: expect.objectContaining({ community: 'public' }),
          device_ids: [1]
        })
      )
    );
  });
});
