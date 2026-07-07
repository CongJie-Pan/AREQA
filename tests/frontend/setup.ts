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

// Stitches/JSDOM cssRules workaround
const originalInsertRule = window.CSSStyleSheet.prototype.insertRule;
window.CSSStyleSheet.prototype.insertRule = function(rule, index) {
  try {
    return originalInsertRule.call(this, rule, index);
  } catch (e) {
    return 0; // Ignore parsing errors in JSDOM
  }
};

try {
  Object.defineProperty(window.CSSStyleSheet.prototype, 'cssRules', {
    get() {
      return [];
    },
    configurable: true
  });
} catch(e) {}

try {
  Object.defineProperty(document, 'styleSheets', {
    value: [
      {
        cssRules: [],
        insertRule: () => 0,
        deleteRule: () => {}
      }
    ],
    configurable: true
  });
} catch(e) {}

try {
  Object.defineProperty(window.HTMLStyleElement.prototype, 'sheet', {
    get() {
      return {
        cssRules: [],
        insertRule: () => 0,
        deleteRule: () => {}
      };
    },
    configurable: true
  });
} catch(e) {}

// Mock Stitches core to prevent JSDOM crashes
vi.mock('@stitches/core', () => ({
  createStitches: vi.fn(() => ({
    styled: vi.fn(),
    css: vi.fn(),
    globalCss: vi.fn(),
    keyframes: vi.fn(),
    getCssText: vi.fn(),
    theme: {},
    config: {},
  })),
}));
