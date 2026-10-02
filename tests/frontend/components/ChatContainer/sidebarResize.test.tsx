import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useSidebarResize } from '@/components/ChatContainer/useSidebarResize';

function Harness() {
  const resize = useSidebarResize();
  return <div role="separator" aria-valuenow={resize.width} aria-valuemax={resize.maxWidth}
    onPointerDown={resize.startResize} onKeyDown={resize.onKeyDown} />;
}

function pointer(target: Element | Window, type: string, clientX: number, pointerId = 1, button = 0) {
  const event = new MouseEvent(type, { bubbles: true, clientX, button });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  fireEvent(target, event);
}

describe('sidebar resizing', () => {
  const originalViewport = window.innerWidth;
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
  });
  afterEach(() => {
    cleanup();
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalViewport });
  });

  it('drags in both directions, bounds the width, and stops on release', () => {
    render(<Harness />);
    const handle = screen.getByRole('separator');
    pointer(handle, 'pointerdown', 280);
    pointer(window, 'pointermove', 400, 2);
    expect(handle).toHaveAttribute('aria-valuenow', '280');
    pointer(window, 'pointermove', 400);
    expect(handle).toHaveAttribute('aria-valuenow', '400');
    pointer(window, 'pointermove', 10000);
    expect(handle).toHaveAttribute('aria-valuenow', '420');
    pointer(window, 'pointermove', -100);
    expect(handle).toHaveAttribute('aria-valuenow', '220');
    pointer(window, 'pointerup', -100);
    pointer(window, 'pointermove', 400);
    expect(handle).toHaveAttribute('aria-valuenow', '220');
    expect(document.body.style.userSelect).toBe('');
  });

  it('restores existing body styles on cancel and unmount', () => {
    document.body.style.cursor = 'crosshair';
    document.body.style.userSelect = 'text';
    const view = render(<Harness />);
    const handle = screen.getByRole('separator');
    pointer(handle, 'pointerdown', 280);
    expect(document.body.style.cursor).toBe('col-resize');
    pointer(window, 'pointercancel', 280);
    expect(document.body.style.cursor).toBe('crosshair');
    expect(document.body.style.userSelect).toBe('text');
    pointer(handle, 'pointerdown', 280);
    view.unmount();
    expect(document.body.style.cursor).toBe('crosshair');
    expect(document.body.style.userSelect).toBe('text');
  });

  it('supports keyboard resizing and adapts to viewport changes without losing the chosen width', () => {
    render(<Harness />);
    const handle = screen.getByRole('separator');
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(handle).toHaveAttribute('aria-valuenow', '296');
    fireEvent.keyDown(handle, { key: 'ArrowLeft' });
    expect(handle).toHaveAttribute('aria-valuenow', '280');
    fireEvent.keyDown(handle, { key: 'End' });
    expect(handle).toHaveAttribute('aria-valuenow', '420');
    expect(handle).toHaveAttribute('aria-valuemax', '420');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 800 });
    act(() => { window.dispatchEvent(new Event('resize')); });
    expect(handle).toHaveAttribute('aria-valuenow', '380');
    expect(handle).toHaveAttribute('aria-valuemax', '380');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
    act(() => { window.dispatchEvent(new Event('resize')); });
    expect(handle).toHaveAttribute('aria-valuenow', '420');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 2560 });
    act(() => { window.dispatchEvent(new Event('resize')); });
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(handle).toHaveAttribute('aria-valuenow', '420');
    expect(handle).toHaveAttribute('aria-valuemax', '420');
    fireEvent.keyDown(handle, { key: 'Home' });
    expect(handle).toHaveAttribute('aria-valuenow', '220');
  });

  it('ignores secondary buttons and mobile drags', () => {
    render(<Harness />);
    const handle = screen.getByRole('separator');
    pointer(handle, 'pointerdown', 280, 1, 2);
    pointer(window, 'pointermove', 400);
    expect(handle).toHaveAttribute('aria-valuenow', '280');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 400 });
    pointer(handle, 'pointerdown', 280);
    pointer(window, 'pointermove', 400);
    expect(handle).toHaveAttribute('aria-valuenow', '280');
  });
});
