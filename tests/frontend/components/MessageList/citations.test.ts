import { describe, expect, it } from 'vitest';
import { normalizeCitationMarkers } from '@/components/MessageList/MessageItem';

describe('normalizeCitationMarkers', () => {
  it('converts Markdown-style 文獻 markers into clickable citation links', () => {
    expect(normalizeCitationMarkers('根據資料[文獻5]，此說法成立。')).toBe(
      '根據資料[5](#cite-5)，此說法成立。',
    );
  });

  it('keeps full-width markers and expands multiple references', () => {
    expect(normalizeCitationMarkers('依據【文獻5、6】。')).toBe(
      '依據[5](#cite-5)[6](#cite-6)。',
    );
  });

  it('does not rewrite an existing Markdown link', () => {
    const content = '[文獻5](https://example.com/source)';
    expect(normalizeCitationMarkers(content)).toBe(content);
  });
});
