import { renderHook, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach, Mock } from 'vitest';
import { useProactiveWebSocket } from '../../../frontend/src/hooks/useProactiveWebSocket';

const flushPromises = () => new Promise(resolve => process.nextTick(resolve));

describe('useProactiveWebSocket', () => {
  let mockWebSocket: any;
  let webSocketInstances: any[] = [];

  beforeEach(() => {
    vi.useFakeTimers();
    webSocketInstances = [];
    
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
    
    const spiedMock = vi.fn(mockWebSocket);
    global.WebSocket = spiedMock as unknown as typeof WebSocket;
    mockWebSocket = spiedMock;

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ticket: 'mock_ticket_123' })
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('connects to websocket with ticket', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    
    expect(mockWebSocket).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ws/notifications?ticket=mock_ticket_123')
    );
  });

  it('calls onAlert when has_alert is true', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    const ws = webSocketInstances[0];
    
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_alert: true, content: 'Test alert' }) });
    }
    
    expect(onAlert).toHaveBeenCalledWith('Test alert', undefined);
  });

  it('calls onNewMail when has_new_mail is true', async () => {
    const onAlert = vi.fn();
    const onNewMail = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert, onNewMail));
    
    await flushPromises();
    const ws = webSocketInstances[0];
    
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_new_mail: true, sender: '蘇格拉底' }) });
    }
    
    expect(onNewMail).toHaveBeenCalledWith('蘇格拉底');
    expect(onAlert).not.toHaveBeenCalled();
  });

  it('does not call onAlert when has_alert is false', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    const ws = webSocketInstances[0];
    
    if (ws.onmessage) {
      ws.onmessage({ data: JSON.stringify({ has_alert: false }) });
    }
    
    expect(onAlert).not.toHaveBeenCalled();
  });

  it('reconnects with exponential backoff on close', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    expect(webSocketInstances.length).toBe(1);
    
    const ws1 = webSocketInstances[0];
    
    if (ws1.onclose) ws1.onclose();
    
    await flushPromises();
    vi.advanceTimersByTime(999);
    await flushPromises();
    expect(webSocketInstances.length).toBe(1); 
    
    vi.advanceTimersByTime(1);
    await flushPromises();
    expect(webSocketInstances.length).toBe(2); 
    
    const ws2 = webSocketInstances[1];
    if (ws2.onclose) ws2.onclose();
    
    await flushPromises();
    vi.advanceTimersByTime(1999);
    await flushPromises();
    expect(webSocketInstances.length).toBe(2);
    
    vi.advanceTimersByTime(1);
    await flushPromises();
    expect(webSocketInstances.length).toBe(3);
  });

  it('resets backoff on successful open', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    const ws1 = webSocketInstances[0];
    
    if (ws1.onclose) ws1.onclose();
    await flushPromises();
    vi.advanceTimersByTime(1000);
    await flushPromises();
    
    const ws2 = webSocketInstances[1];
    if (ws2.onopen) ws2.onopen();
    
    if (ws2.onclose) ws2.onclose();
    await flushPromises();
    
    vi.advanceTimersByTime(1000);
    await flushPromises();
    expect(webSocketInstances.length).toBe(3);
  });
});
