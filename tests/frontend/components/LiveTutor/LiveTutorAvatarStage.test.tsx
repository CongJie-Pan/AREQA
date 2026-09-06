import React from 'react';
import { fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  });

  it('shows the AREQA logo fallback when avatar is disabled or not ready', () => {
    const { container, rerender } = render(
      <LiveTutorAvatarStage avatarEnabled={false} avatarStream={avatarStream()} status="listening" />,
    );

    expect(container.querySelector('img')).toHaveAttribute('src', '/icon/areqa_icon_v4_circle.png');
    expect(document.querySelector('video')).not.toBeInTheDocument();

    rerender(<LiveTutorAvatarStage avatarEnabled avatarStream={null} status="listening" />);

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
});
