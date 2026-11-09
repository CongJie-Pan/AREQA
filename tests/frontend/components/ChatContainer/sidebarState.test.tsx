import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSidebarState } from '@/components/ChatContainer/useSidebarState';

vi.mock('@/utils/logger', () => ({ logger: { debug: vi.fn() } }));
const originalMatchMedia = window.matchMedia;
let mobile = false;
const listeners = new Set<() => void>();

beforeEach(() => {
  mobile = false;
  window.matchMedia = vi.fn().mockImplementation(() => ({
    get matches() { return mobile; },
    addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
  }));
});
afterEach(() => { cleanup(); window.matchMedia = originalMatchMedia; listeners.clear(); });
const viewport = (value: boolean) => act(() => { mobile = value; listeners.forEach(listener => listener()); });

describe('responsive sidebar state', () => {
  it('starts open on desktop and closed on mobile', () => {
    const { result } = renderHook(useSidebarState);
    expect(result.current.isOpen).toBe(true);
    viewport(true);
    expect(result.current.isOpen).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.isOpen).toBe(true);
    act(() => result.current.toggle());
    expect(result.current.isOpen).toBe(false);
  });

  it('keeps desktop collapse and mobile drawer choices independent across breakpoints', () => {
    const { result } = renderHook(useSidebarState);
    act(() => result.current.toggle());
    expect(result.current.desktopCollapsed).toBe(true);
    viewport(true);
    expect(result.current.isOpen).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.mobileOpen).toBe(true);
    viewport(false);
    expect(result.current.isOpen).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.isOpen).toBe(true);
    viewport(true);
    expect(result.current.isOpen).toBe(true);
  });

  it('closes mobile navigation after selection without changing desktop visibility', () => {
    const { result } = renderHook(useSidebarState);
    act(() => result.current.closeMobile());
    expect(result.current.isOpen).toBe(true);
    viewport(true);
    act(() => result.current.toggle());
    act(() => result.current.closeMobile());
    expect(result.current.isOpen).toBe(false);
    viewport(false);
    expect(result.current.isOpen).toBe(true);
  });
});
