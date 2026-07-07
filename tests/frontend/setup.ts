import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock scrollTo as it's not implemented in JSDOM
Element.prototype.scrollTo = vi.fn();
Element.prototype.scrollIntoView = vi.fn();

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverMock as any;
window.ResizeObserver = ResizeObserverMock as any;

// Mock CSSStyleSheet insertRule to prevent Stitches parsing errors in JSDOM
if (typeof window !== 'undefined' && window.CSSStyleSheet && window.CSSStyleSheet.prototype) {
  window.CSSStyleSheet.prototype.insertRule = function() { return 0; };
  try {
    Object.defineProperty(window.CSSStyleSheet.prototype, 'cssRules', {
      get: function() { return []; },
      configurable: true
    });
  } catch (e) {}
}
