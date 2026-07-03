import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach, Mock } from 'vitest';
import { useProactiveWebSocket } from '../../../frontend/src/hooks/useProactiveWebSocket';

describe('useProactiveWebSocket', () => {
  let mockWebSocket: any;
  let webSocketInstances: any[] = [];

  beforeEach(() => {
    vi.useFakeTimers();
    webSocketInstances = [];
    
    // Mock WebSocket globally
    const OriginalWebSocket = global.WebSocket;
    
    mockWebSocket = function(url: string) {
      const instance = {
        url,
        close: vi.fn(),
        send: vi.fn(),
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
      };
      webSocketInstances.push(instance);
      return instance;
    };
    
    // Track calls on the constructor if needed, though not strictly required
    const spiedMock = vi.fn(mockWebSocket);
    
    global.WebSocket = spiedMock as unknown as typeof WebSocket;
    mockWebSocket = spiedMock; // So the tests can assert on it
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('connects to websocket with default_user', () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    expect(mockWebSocket).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ws/notifications?user_id=default_user')
    );
  });

  it('calls onAlert when has_alert is true', () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    const ws = webSocketInstances[0];
    
    // Simulate incoming message
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_alert: true, content: 'Test alert' }) });
    }
    
    expect(onAlert).toHaveBeenCalledWith('Test alert', undefined);
  });

  it('calls onNewMail when has_new_mail is true', () => {
    const onAlert = vi.fn();
    const onNewMail = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert, onNewMail));
    
    const ws = webSocketInstances[0];
    
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_new_mail: true, sender: '蘇格拉底' }) });
    }
    
    expect(onNewMail).toHaveBeenCalledWith('蘇格拉底');
    expect(onAlert).not.toHaveBeenCalled();
  });

  it('does not call onAlert when has_alert is false', () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    const ws = webSocketInstances[0];
    
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_alert: false }) });
    }
    
    expect(onAlert).not.toHaveBeenCalled();
  });

  it('reconnects with exponential backoff on close', () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    expect(webSocketInstances.length).toBe(1);
    
    const ws1 = webSocketInstances[0];
    
    // Trigger first close -> should wait 1s (1000ms)
    if (ws1.onclose) ws1.onclose();
    
    vi.advanceTimersByTime(999);
    expect(webSocketInstances.length).toBe(1); // not yet
    
    vi.advanceTimersByTime(1);
    expect(webSocketInstances.length).toBe(2); // 1st reconnect
    
    const ws2 = webSocketInstances[1];
    
    // Trigger second close -> should wait 2s (2000ms)
    if (ws2.onclose) ws2.onclose();
    
    vi.advanceTimersByTime(1999);
    expect(webSocketInstances.length).toBe(2);
    
    vi.advanceTimersByTime(1);
    expect(webSocketInstances.length).toBe(3); // 2nd reconnect
  });

  it('resets backoff on successful open', () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    const ws1 = webSocketInstances[0];
    
    // Simulate close to increase backoff to 2000
    if (ws1.onclose) ws1.onclose();
    vi.advanceTimersByTime(1000);
    
    const ws2 = webSocketInstances[1];
    
    // Successful open resets backoff to 1000
    if (ws2.onopen) ws2.onopen();
    
    // Simulate close again -> should wait 1s (1000ms) because it reset, not 2s
    if (ws2.onclose) ws2.onclose();
    
    vi.advanceTimersByTime(1000);
    expect(webSocketInstances.length).toBe(3);
  });
});
