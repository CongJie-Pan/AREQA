import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useTextSelection } from '@/hooks/useTextSelection';

describe('useTextSelection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock getSelection
    window.getSelection = vi.fn().mockReturnValue({
      isCollapsed: true,
      toString: () => '',
      removeAllRanges: vi.fn(),
      getRangeAt: vi.fn().mockReturnValue({
        getBoundingClientRect: () => ({
          top: 100,
          left: 100,
          width: 50,
          height: 20,
        }),
      }),
    });
  });

  it('should initialize with empty selection', () => {
    const { result } = renderHook(() => useTextSelection());
    expect(result.current.text).toBe('');
    expect(result.current.rect).toBeNull();
  });

  it('should update selection when text is selected within an AI bubble', () => {
    // Mock elements
    const bubble = document.createElement('div');
    bubble.setAttribute('data-role', 'assistant-bubble');
    const textNode = document.createTextNode('selected text');
    bubble.appendChild(textNode);
    document.body.appendChild(bubble);

    const mockSelection = {
      isCollapsed: false,
      toString: () => 'selected text',
      anchorNode: textNode,
      focusNode: textNode,
      getRangeAt: vi.fn().mockReturnValue({
        getBoundingClientRect: () => ({
          top: 100,
          left: 100,
          width: 50,
          height: 20,
        }),
      }),
    };
    window.getSelection = vi.fn().mockReturnValue(mockSelection);

    const { result } = renderHook(() => useTextSelection());

    act(() => {
      document.dispatchEvent(new Event('selectionchange'));
    });

    expect(result.current.text).toBe('selected text');
    expect(result.current.rect).toEqual({
      top: 100,
      left: 100,
      width: 50,
      height: 20,
    });

    document.body.removeChild(bubble);
  });

  it('should ignore selection if outside an AI bubble', () => {
    // Mock elements without data-role
    const div = document.createElement('div');
    const textNode = document.createTextNode('user text');
    div.appendChild(textNode);
    document.body.appendChild(div);

    const mockSelection = {
      isCollapsed: false,
      toString: () => 'user text',
      anchorNode: textNode,
      focusNode: textNode,
      getRangeAt: vi.fn(),
    };
    window.getSelection = vi.fn().mockReturnValue(mockSelection);

    const { result } = renderHook(() => useTextSelection());

    act(() => {
      document.dispatchEvent(new Event('selectionchange'));
    });

    expect(result.current.text).toBe('');
    expect(result.current.rect).toBeNull();

    document.body.removeChild(div);
  });

  it('should clear selection when isCollapsed is true', () => {
    // Mock elements
    const bubble = document.createElement('div');
    bubble.setAttribute('data-role', 'assistant-bubble');
    const textNode = document.createTextNode('text');
    bubble.appendChild(textNode);
    document.body.appendChild(bubble);

    const { result } = renderHook(() => useTextSelection());

    // First set a selection
    window.getSelection = vi.fn().mockReturnValue({
      isCollapsed: false,
      toString: () => 'text',
      anchorNode: textNode,
      focusNode: textNode,
      getRangeAt: vi.fn().mockReturnValue({
        getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }),
      }),
    });
    act(() => {
      document.dispatchEvent(new Event('selectionchange'));
    });
    expect(result.current.text).toBe('text');

    // Then collapse it
    window.getSelection = vi.fn().mockReturnValue({
      isCollapsed: true,
      toString: () => '',
    });
    act(() => {
      document.dispatchEvent(new Event('selectionchange'));
    });

    expect(result.current.text).toBe('');
    expect(result.current.rect).toBeNull();

    document.body.removeChild(bubble);
  });

  it('should ignore selection if active element is an input', () => {
    const { result } = renderHook(() => useTextSelection());

    // Mock active element as input
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    window.getSelection = vi.fn().mockReturnValue({
      isCollapsed: false,
      toString: () => 'text',
    });

    act(() => {
      document.dispatchEvent(new Event('selectionchange'));
    });

    expect(result.current.text).toBe('');
    
    document.body.removeChild(input);
  });
});
