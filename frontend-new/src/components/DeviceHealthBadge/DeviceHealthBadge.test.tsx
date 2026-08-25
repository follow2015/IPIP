import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DeviceHealthBadge from './DeviceHealthBadge';
import type { DeviceMonitorStatusData } from '@/services/monitor';

const getMock = vi.fn();
vi.mock('@/services/api-client', () => ({
  get: (...args: unknown[]) => getMock(...args)
}));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false
      }
    }
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const basePayload: DeviceMonitorStatusData = {
  monitored: true,
  configured_protocols: ['snmp'],
  status: {
    id: 1,
    device_id: 12,
    protocol: 'snmp',
    reachable: true,
    ever_reachable: true,
    down_alerted: false,
    down_episode: 0,
    last_reachable_at: '2026-07-29T10:00:00',
    last_unreachable_at: null,
    last_checked_at: '2026-07-29T10:00:30',
    consecutive_failures: 0,
    latency_ms: 12,
    extra: null,
    last_error: null
  }
};

describe('DeviceHealthBadge', () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it('reachable=true → 渲染绿色徽标（可达）', async () => {
    getMock.mockResolvedValue({ data: basePayload });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      const tag = container.querySelector('.ant-tag');
      expect(tag).not.toBeNull();
      expect(tag!.className).toContain('ant-tag-green');
      expect(tag).toHaveTextContent('可达');
    });
  });

  it('reachable=false → 渲染红色徽标（不可达 + 上次可达：）', async () => {
    const payload: DeviceMonitorStatusData = {
      ...basePayload,
      status: { ...basePayload.status!, reachable: false }
    };
    getMock.mockResolvedValue({ data: payload });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      const tag = container.querySelector('.ant-tag');
      expect(tag).not.toBeNull();
      expect(tag!.className).toContain('ant-tag-red');
      expect(tag).toHaveTextContent('不可达');
      expect(tag).toHaveTextContent('上次可达：');
    });
  });

  it('monitored=false（无凭据）→ 不渲染任何内容', async () => {
    getMock.mockResolvedValue({
      data: { monitored: false, configured_protocols: [], status: null }
    });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(container.querySelector('.ant-tag')).toBeNull();
      expect(container.innerHTML).toBe('');
    });
  });

  it('护栏：monitored=true 但 status=null → 不渲染 .ant-tag', async () => {
    getMock.mockResolvedValue({
      data: { monitored: true, configured_protocols: ['snmp'], status: null }
    });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(container.querySelector('.ant-tag')).toBeNull();
    });
  });

  it('monitor_interrupted=true → 渲染橙色中断 Tag', async () => {
    const payload: DeviceMonitorStatusData = {
      ...basePayload,
      monitor_interrupted: true
    };
    getMock.mockResolvedValue({ data: payload });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      const tags = container.querySelectorAll('.ant-tag');
      expect(tags.length).toBeGreaterThanOrEqual(1);
      const interruptedTag = Array.from(tags).find((t) => t.textContent?.includes('中断'));
      expect(interruptedTag).toBeDefined();
      expect(interruptedTag!.className).toContain('ant-tag-orange');
    });
  });

  it('active_metric_alerts>0 → 渲染指标告警 Tag', async () => {
    const payload: DeviceMonitorStatusData = {
      ...basePayload,
      active_metric_alerts: 3,
      max_alert_severity: 2
    };
    getMock.mockResolvedValue({ data: payload });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      const tags = container.querySelectorAll('.ant-tag');
      const alertTag = Array.from(tags).find((t) => t.textContent?.includes('指标告警'));
      expect(alertTag).toBeDefined();
      expect(alertTag).toHaveTextContent('指标告警 3');
    });
  });

  it('active_metric_alerts>0 且 max_alert_severity>=3 → magenta 色', async () => {
    const payload: DeviceMonitorStatusData = {
      ...basePayload,
      active_metric_alerts: 1,
      max_alert_severity: 3
    };
    getMock.mockResolvedValue({ data: payload });
    const { container } = render(<DeviceHealthBadge deviceId={12} />, { wrapper: makeWrapper() });

    await waitFor(() => {
      const tags = container.querySelectorAll('.ant-tag');
      const alertTag = Array.from(tags).find((t) => t.textContent?.includes('指标告警'));
      expect(alertTag!.className).toContain('ant-tag-magenta');
    });
  });
});
