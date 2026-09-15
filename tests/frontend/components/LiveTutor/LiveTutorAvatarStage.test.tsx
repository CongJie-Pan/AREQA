import React from 'react';
import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveTutorAvatarStage } from '@/components/LiveTutor/LiveTutorAvatarStage';

vi.mock('next/image', () => ({
  default: ({ alt, ...props }: { alt: string; src: string }) => <img alt={alt} {...props} />,
}));

function avatarStream(): MediaStream {
  return {
    getVideoTracks: () => [{ readyState: 'live' }],
    getAudioTracks: () => [],
    getTracks: () => [],
  } as unknown as MediaStream;
}

describe('LiveTutorAvatarStage', () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the AREQA logo fallback when avatar is disabled or not ready', () => {
    const { container, rerender } = render(
      <LiveTutorAvatarStage avatarEnabled={false} avatarStream={avatarStream()} status="listening" />,
    );

    expect(container.firstElementChild).toHaveAttribute('data-avatar-state', 'fallback');
    expect(container.querySelector('img')).toHaveAttribute('src', '/icon/areqa_icon_v4_circle.png');
    expect(document.querySelector('video')).not.toBeInTheDocument();

    rerender(<LiveTutorAvatarStage avatarEnabled avatarStream={null} status="listening" />);

    expect(container.firstElementChild).toHaveAttribute('data-avatar-state', 'waiting');
    expect(container.querySelector('img')).toHaveAttribute('src', '/icon/areqa_icon_v4_circle.png');
  });

  it('crossfades to avatar video after the remote video track loads', () => {
    const { container } = render(<LiveTutorAvatarStage avatarEnabled avatarStream={avatarStream()} status="speaking" />);

    const video = document.querySelector('video');
    expect(video).toBeInTheDocument();
    expect(video).toHaveAttribute('playsinline');
    expect(container.querySelector('img')).toBeInTheDocument();

    fireEvent.loadedData(video as HTMLVideoElement);

    expect(container.querySelector('img')).not.toBeInTheDocument();
  });

  it('falls back and reports an unhealthy stream when avatar video stalls', async () => {
    vi.useFakeTimers();
    const onStreamUnhealthy = vi.fn();
    const { container } = render(
      <LiveTutorAvatarStage
        avatarEnabled
        avatarStream={avatarStream()}
        status="speaking"
        onStreamUnhealthy={onStreamUnhealthy}
      />,
    );
    const video = document.querySelector('video') as HTMLVideoElement;

    fireEvent.loadedData(video);
    expect(container.querySelector('img')).not.toBeInTheDocument();
    fireEvent.stalled(video);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });

    expect(onStreamUnhealthy).toHaveBeenCalledOnce();
    expect(container.firstElementChild).toHaveAttribute('data-avatar-state', 'waiting');
    expect(container.querySelector('img')).toBeInTheDocument();
  });
});
