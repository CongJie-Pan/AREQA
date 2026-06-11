import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ScreenObserver from '../../../frontEnd/src/components/ScreenObserver';
import { useStore } from '../../../frontEnd/src/store/useStore';

// Mock the store
vi.mock('../../../frontEnd/src/store/useStore', () => ({
  useStore: vi.fn(),
}));

describe('ScreenObserver', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock navigator.mediaDevices.getDisplayMedia
    Object.defineProperty(global.navigator, 'mediaDevices', {
      value: {
        getDisplayMedia: vi.fn().mockResolvedValue({
          getVideoTracks: () => [{ onended: vi.fn() }],
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
      configurable: true,
    });
    
    // Default store state
    (useStore as unknown as any).mockReturnValue({
      isRecording: true,
      enableScreenCapture: true,
    });

    // Mock HTMLMediaElement.prototype.play
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  });

  it('should not use display: none on the wrapper div to prevent Chromium black screen bug', () => {
    const { container } = render(<ScreenObserver />);
    const wrapperDiv = container.firstChild as HTMLDivElement;
    
    // Check that it does not use display: none
    expect(wrapperDiv.style.display).not.toBe('none');
    
    // Verify it uses the off-screen/invisible trick instead
    expect(wrapperDiv.style.position).toBe('fixed');
    expect(wrapperDiv.style.opacity).toBe('0.01');
    expect(wrapperDiv.style.pointerEvents).toBe('none');
  });

  it('should not capture frame if video readyState is less than 2 (HAVE_CURRENT_DATA)', async () => {
    // Setup canvas mock
    const mockDrawImage = vi.fn();
    const mockToDataURL = vi.fn().mockReturnValue('data:image/jpeg;base64,mock');
    const mockGetContext = vi.fn().mockReturnValue({
      drawImage: mockDrawImage,
    });
    
    // Intercept Canvas elements
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName.toLowerCase() === 'canvas') {
        (el as HTMLCanvasElement).getContext = mockGetContext as any;
        (el as HTMLCanvasElement).toDataURL = mockToDataURL;
      }
      return el;
    });

    render(<ScreenObserver />);

    // Wait for stream to attach (we need to give it a tick)
    await new Promise(resolve => setTimeout(resolve, 0));

    // Fast-forward setInterval by 6000ms to trigger captureAndSendFrame
    // But since we can't easily fake the video element's readyState via ref in RTL directly without injecting,
    // let's grab the video element and mock its properties
    const videoElements = document.getElementsByTagName('video');
    expect(videoElements.length).toBe(1);
    
    const video = videoElements[0];
    
    // Override read-only properties
    Object.defineProperty(video, 'videoWidth', { value: 1920, configurable: true });
    Object.defineProperty(video, 'videoHeight', { value: 1080, configurable: true });
    Object.defineProperty(video, 'readyState', { value: 1, configurable: true }); // HAVE_METADATA only

    // We can't access the internal captureAndSendFrame easily, so let's mock the setInterval
    vi.useFakeTimers();
    render(<ScreenObserver />); // Re-render to pick up fake timers
    
    // Apply video properties to new video element
    const newVideo = document.getElementsByTagName('video')[0];
    Object.defineProperty(newVideo, 'videoWidth', { value: 1920, configurable: true });
    Object.defineProperty(newVideo, 'videoHeight', { value: 1080, configurable: true });
    Object.defineProperty(newVideo, 'readyState', { value: 1, configurable: true });

    // Advance 6 seconds
    vi.advanceTimersByTime(6000);
    
    // Restore timers before assertions
    vi.useRealTimers();

    // Since readyState is 1 (< 2), drawImage should NOT have been called!
    expect(mockDrawImage).not.toHaveBeenCalled();
  });
});
