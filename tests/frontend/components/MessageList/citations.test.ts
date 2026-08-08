import { describe, expect, it } from 'vitest';
import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { Citations } from '@/components/Citations';
import { normalizeCitationMarkers, splitMarkdownRevealRows } from '@/components/MessageList/MessageItem';

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

describe('splitMarkdownRevealRows', () => {
  it('creates top-level reveal rows without splitting structural Markdown blocks', () => {
    expect(splitMarkdownRevealRows([
      '# 標題',
      '',
      '第一段內容',
      '',
      '- 重點一',
      '- 重點二',
      '',
      '```ts',
      'const value = 1;',
      '```',
    ].join('\n'))).toEqual([
      '# 標題',
      '第一段內容',
      '- 重點一\n- 重點二',
      '```ts\nconst value = 1;\n```',
    ]);
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

  it('renders source card text as safe Markdown', () => {
    render(React.createElement(Citations, {
      messageId: 'msg-markdown',
      sources: [{
        title: '**NASA** Starship Reference',
        chunk_id: 'https://example.com/markdown-source',
        url: 'https://example.com/markdown-source',
        snippet: 'Includes **bold evidence** and [paper](https://example.com/paper). [bad](javascript:alert(1))',
      }],
      defaultExpanded: true,
    }));

    expect(screen.getByText('NASA').tagName).toBe('STRONG');
    expect(screen.getByText('bold evidence').tagName).toBe('STRONG');
    expect(screen.getByRole('link', { name: 'paper' })).toHaveAttribute(
      'href',
      'https://example.com/paper',
    );
    expect(screen.getByText('bad').closest('a')).toBeNull();
  });

  it('renders Markdown list items inside source cards', () => {
    render(React.createElement(Citations, {
      messageId: 'msg-list',
      sources: [{
        title: 'Markdown List Source',
        chunk_id: 'https://example.com/list-source',
        url: 'https://example.com/list-source',
        snippet: '- 第一點\n- 第二點\n\n1. 第一項\n2. 第二項',
      }],
      defaultExpanded: true,
    }));

    expect(screen.getByText('第一點').tagName).toBe('LI');
    expect(screen.getByText('第二點').tagName).toBe('LI');
    expect(screen.getByText('第一項').tagName).toBe('LI');
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
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
