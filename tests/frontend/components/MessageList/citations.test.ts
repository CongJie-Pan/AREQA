import { describe, expect, it } from 'vitest';
import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { Citations } from '@/components/Citations';
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

describe('Citations structured sources', () => {
  const sources = [{
    title: 'NASA Starship Reference',
    chunk_id: 'https://example.com/source',
    url: 'https://example.com/source',
    snippet: 'Structured source snippet.',
    score: 1,
  }];

  it('renders source title and a safe external URL action', () => {
    render(React.createElement(Citations, {
      messageId: 'msg-1',
      sources,
      defaultExpanded: true,
    }));

    expect(screen.getByText('NASA Starship Reference')).toBeInTheDocument();
    const link = screen.getByTitle('在新分頁開啟原文');
    expect(link).toHaveAttribute('href', 'https://example.com/source');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('opens only in-range citations for the same message', async () => {
    render(React.createElement(Citations, {
      messageId: 'msg-2',
      sources,
      defaultExpanded: true,
    }));

    await act(async () => {
      window.dispatchEvent(new CustomEvent('open-citation-msg-2', { detail: { index: 2 } }));
    });
    expect(screen.queryByText('來源: https://example.com/source')).not.toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(new CustomEvent('open-citation-msg-2', { detail: { index: 1 } }));
    });
    expect(await screen.findByText('來源: https://example.com/source')).toBeInTheDocument();
    const modalSourceLink = await screen.findByTitle('https://example.com/source');
    expect(modalSourceLink).toHaveAttribute('href', 'https://example.com/source');
    const modalOpenButton = await screen.findByTitle('在新分頁開啟文獻原文');
    expect(modalOpenButton).toHaveAttribute('href', 'https://example.com/source');
  });
});
