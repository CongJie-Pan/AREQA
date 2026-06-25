import React from 'react';
import { render, act, waitFor } from '@testing-library/react';
import { ProactiveManager } from '@/components/ProactiveManager';
import { App } from 'antd';
import { sendMessage } from '@/services/chat';
import { useConversationStore } from '@/store/conversation';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock dependencies
vi.mock('antd', () => ({
  App: {
    useApp: vi.fn(),
  },
}));

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn(),
}));

vi.mock('@/store/conversation', () => ({
  useConversationStore: {
    getState: vi.fn(),
  },
}));

describe('ProactiveManager', () => {
  const mockNotificationInfo = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    global.fetch = vi.fn();
    (App.useApp as any).mockReturnValue({
      notification: {
        info: mockNotificationInfo,
      },
    });

    (useConversationStore.getState as any).mockReturnValue({
      activeConversationId: 'test-convo-id',
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should not show notification if no alert is present', async () => {
    (global.fetch as any).mockResolvedValue({
      json: async () => ({ has_alert: false }),
    });

    render(<ProactiveManager />);

    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/proactive-check?user_id=default_user');

    expect(mockNotificationInfo).not.toHaveBeenCalled();
  });

  it('should show notification when alert is present', async () => {
    const ALERT_CONTENT = 'You seem stuck, want some help?';
    (global.fetch as any).mockResolvedValue({
      json: async () => ({ has_alert: true, content: ALERT_CONTENT }),
    });

    render(<ProactiveManager />);

    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    expect(mockNotificationInfo).toHaveBeenCalled();

    const callArgs = mockNotificationInfo.mock.calls[0][0];
    expect(callArgs.message).toBe('AREQA關心您');
    expect(callArgs.description).toBe(ALERT_CONTENT);

    // Test clicking the notification
    callArgs.onClick();
    expect(sendMessage).toHaveBeenCalledWith(ALERT_CONTENT, 'test-convo-id');
  });

  it('should log scroll action with throttling', async () => {
    (global.fetch as any).mockResolvedValue({
      json: async () => ({ status: 'ok' }),
    });

    render(<ProactiveManager />);

    // Simulate scroll
    Object.defineProperty(window, 'scrollY', { value: 500, configurable: true });
    
    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });

    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/log_action', expect.any(Object));

    const fetchOpts = (global.fetch as any).mock.calls[0][1];
    const body = JSON.parse(fetchOpts.body);
    expect(body.action_type).toBe('scroll');
    expect(body.context.scrollY).toBe(500);

    // Clear mock
    (global.fetch as any).mockClear();

    // Trigger scroll again immediately (should be throttled)
    act(() => {
      window.dispatchEvent(new Event('scroll'));
    });

    expect(global.fetch).not.toHaveBeenCalled();

    // Advance time beyond throttle
    act(() => {
      vi.advanceTimersByTime(6000);
      window.dispatchEvent(new Event('scroll'));
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
