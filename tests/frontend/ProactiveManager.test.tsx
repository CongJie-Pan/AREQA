import React from 'react';
import { render, act } from '@testing-library/react';
import { ProactiveManager } from '@/components/ProactiveManager';
import { App } from 'antd';
import { sendMessage } from '@/services/chat';
import { useConversationStore } from '@/store/conversation';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as hooks from '@/hooks/useProactiveWebSocket';

// Mock dependencies
vi.mock('antd', () => ({
  App: {
    useApp: vi.fn(),
  },
  Button: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
}));

vi.mock('@ant-design/icons', () => ({
  BulbOutlined: () => <span>Bulb</span>,
  CheckOutlined: () => <span>Check</span>,
  CloseOutlined: () => <span>Close</span>,
}));

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn(),
}));

vi.mock('@/store/conversation', () => ({
  useConversationStore: {
    getState: vi.fn(),
  },
}));

vi.mock('@/hooks/useProactiveWebSocket', () => ({
  useProactiveWebSocket: vi.fn(),
}));

const { mockFetchMails } = vi.hoisted(() => ({
  mockFetchMails: vi.fn(),
}));

vi.mock('@/store/mailbox', () => ({
  useMailboxStore: {
    getState: () => ({
      fetchMails: mockFetchMails,
    }),
  },
}));

describe('ProactiveManager', () => {
  const mockNotificationInfo = vi.fn();
  const mockNotificationDestroy = vi.fn();
  let registeredAlertCallback: ((content: string) => void) | null = null;
  let registeredNewMailCallback: (() => void) | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    global.fetch = vi.fn();
    (App.useApp as any).mockReturnValue({
      notification: {
        info: mockNotificationInfo,
        destroy: mockNotificationDestroy,
      },
    });

    (useConversationStore.getState as any).mockReturnValue({
      activeConversationId: 'test-convo-id',
    });

    // Capture the callback passed to the hook
    registeredAlertCallback = null;
    registeredNewMailCallback = null;
    (hooks.useProactiveWebSocket as any).mockImplementation((callback: any, onNewMail: any) => {
      registeredAlertCallback = callback;
      registeredNewMailCallback = onNewMail;
      return false;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should not show notification initially', async () => {
    render(<ProactiveManager />);
    expect(mockNotificationInfo).not.toHaveBeenCalled();
  });

  it('should ignore legacy websocket alerts because care now arrives by mailbox', async () => {
    render(<ProactiveManager />);

    expect(registeredAlertCallback).toBeTruthy();

    const ALERT_CONTENT = 'AREQA發現你好像來回看了幾遍...';
    
    act(() => {
      if (registeredAlertCallback) {
        registeredAlertCallback(ALERT_CONTENT);
      }
    });

    expect(mockNotificationInfo).not.toHaveBeenCalled();
  });

  it('should log scroll action with throttling', async () => {
    (global.fetch as any).mockResolvedValue({
      json: async () => ({ status: 'ok' }),
    });

    render(<ProactiveManager />);

    // Simulate first scroll to initialize lastScrollY
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });
    
    // Simulate second scroll to trigger logAction
    Object.defineProperty(window, 'scrollY', { value: 500, configurable: true });
    await act(async () => {
      vi.advanceTimersByTime(5001); // Wait for debounce
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

    // Advance time beyond throttle and change scroll position
    await act(async () => {
      vi.advanceTimersByTime(6000);
      Object.defineProperty(window, 'scrollY', { value: 1000, configurable: true });
      window.dispatchEvent(new Event('scroll'));
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('should register a mailbox refresh callback for new-mail events', async () => {
    render(<ProactiveManager />);
    expect(registeredNewMailCallback).toBeTypeOf('function');
  });

  it('refreshes mailbox only when websocket reports new mail', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    await act(async () => {
      render(<ProactiveManager />);
      await Promise.resolve();
    });

    expect(intervalSpy).not.toHaveBeenCalled();
    expect(mockFetchMails).not.toHaveBeenCalled();

    await act(async () => {
      registeredNewMailCallback?.();
      await vi.dynamicImportSettled();
      await Promise.resolve();
    });

    expect(mockFetchMails).toHaveBeenCalledTimes(1);
  });
});
