import { describe, expect, it } from 'vitest';

import manifest from '../../../frontend/src/app/manifest';

describe('PWA manifest icons', () => {
  it('uses the v4 install icons for mobile home-screen installs', () => {
    const iconSources = manifest().icons?.map((icon) => icon.src) ?? [];

    expect(iconSources).toEqual([
      '/icon/areqa_icon_v4_192.png',
      '/icon/areqa_icon_v4_512.png',
      '/icon/areqa_icon_v4_maskable_512.png',
    ]);
    expect(iconSources.some((source) => source.includes('v3'))).toBe(false);
  });
});
