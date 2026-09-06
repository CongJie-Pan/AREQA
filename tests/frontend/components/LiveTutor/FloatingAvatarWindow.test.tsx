import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FloatingAvatarWindow } from '@/components/LiveTutor/FloatingAvatarWindow';

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
  },
}));

const STORAGE_KEY = 'areqa:live-tutor-avatar-window-position';

function avatarStream(): MediaStream {
  return {
    getVideoTracks: () => [{ readyState: 'live' }],
    getAudioTracks: () => [],
    getTracks: () => [],
  } as unknown as MediaStream;
}

function setViewport(width: number, height: number): void {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true });
  Object.defineProperty(window, 'matchMedia', {
    value: vi.fn((query: string) => ({
      matches: query.includes('max-width') && width <= 768,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
    configurable: true,
  });
}

function installPointerCapture(): void {
  Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
    value: vi.fn(),
    configurable: true,
  });
  Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
    value: vi.fn(() => true),
    configurable: true,
  });
  Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
    value: vi.fn(),
    configurable: true,
  });
}

describe('FloatingAvatarWindow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    setViewport(1200, 800);
    installPointerCapture();
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  });

  it('renders a fixed avatar video window and attaches the remote stream', async () => {
    const stream = avatarStream();
    const { container } = render(<FloatingAvatarWindow stream={stream} status="listening" />);

    const windowNode = container.querySelector('[data-avatar-window="floating"]');
    const video = screen.getByLabelText('AREQA avatar video') as HTMLVideoElement;

    expect(windowNode).toBeInTheDocument();
    expect(video).toHaveAttribute('playsinline');
    await waitFor(() => expect(video.srcObject).toBe(stream));
  });

  it('persists desktop drag position after the handle is moved', async () => {
    const { container } = render(<FloatingAvatarWindow stream={avatarStream()} status="speaking" />);
    const windowNode = container.querySelector('[data-avatar-window="floating"]') as HTMLDivElement;
    windowNode.getBoundingClientRect = () => ({
      x: 100,
      y: 100,
      top: 100,
      left: 100,
      right: 340,
      bottom: 400,
      width: 240,
      height: 300,
      toJSON: () => ({}),
    });

    const handle = screen.getByLabelText('Move avatar window');
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 110, clientY: 112 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 300, clientY: 320 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: 300, clientY: 320 });

    await waitFor(() => {
      expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null')).toEqual({ x: 290, y: 308 });
    });
  });
});
