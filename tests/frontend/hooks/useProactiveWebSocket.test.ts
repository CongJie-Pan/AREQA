import { act, renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach, Mock } from 'vitest';
import { useProactiveWebSocket } from '../../../frontend/src/hooks/useProactiveWebSocket';

const flushPromises = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

describe('useProactiveWebSocket', () => {
  let mockWebSocket: any;
  let webSocketInstances: any[] = [];

  beforeEach(() => {
    vi.useFakeTimers();
    webSocketInstances = [];
    localStorage.setItem(
      'test-auth-token',
      JSON.stringify({ access_token: 'test-access-token', user: { id: 'test-user' } })
    );
    
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
    localStorage.clear();
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

  it('returns false until websocket opens', async () => {
    const onAlert = vi.fn();
    const { result } = renderHook(() => useProactiveWebSocket(onAlert));

    expect(result.current).toBe(false);

    await flushPromises();

    expect(result.current).toBe(false);
  });

  it('returns websocket connection status after open and close', async () => {
    const onAlert = vi.fn();
    const { result } = renderHook(() => useProactiveWebSocket(onAlert));

    await flushPromises();
    const ws = webSocketInstances[0];

    await act(async () => {
      if (ws.onopen) ws.onopen();
    });

    expect(result.current).toBe(true);

    await act(async () => {
      if (ws.onclose) ws.onclose();
    });

    expect(result.current).toBe(false);
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
    await act(async () => vi.advanceTimersByTimeAsync(999));
    expect(webSocketInstances.length).toBe(1); 
    
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(webSocketInstances.length).toBe(2); 
    
    const ws2 = webSocketInstances[1];
    if (ws2.onclose) ws2.onclose();
    
    await flushPromises();
    await act(async () => vi.advanceTimersByTimeAsync(1999));
    expect(webSocketInstances.length).toBe(2);
    
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(webSocketInstances.length).toBe(3);
  });

  it('resets backoff on successful open', async () => {
    const onAlert = vi.fn();
    renderHook(() => useProactiveWebSocket(onAlert));
    
    await flushPromises();
    const ws1 = webSocketInstances[0];
    
    if (ws1.onclose) ws1.onclose();
    await flushPromises();
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    
    const ws2 = webSocketInstances[1];
    await act(async () => {
      if (ws2.onopen) ws2.onopen();
    });
    
    await act(async () => {
      if (ws2.onclose) ws2.onclose();
    });
    
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(webSocketInstances.length).toBe(3);
  });
});
