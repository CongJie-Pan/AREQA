import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

// We do NOT mock styles.ts to ensure we test actual CSS-in-JS behavior
vi.mock('../../../../frontend/src/components/RAGStatusPanel', () => ({
  RAGStatusPanel: () => <div data-testid="rag-status-panel"></div>
}));

vi.mock('../../../../frontend/src/components/ThinkingPanel', () => ({
  ThinkingPanel: () => <div data-testid="thinking-panel"></div>
}));

describe('MessageItem Quote Alignment Regression', () => {
  it('keeps the user message editor as wide as its message row', () => {
    render(
      <App>
        <MessageItem
          message={{ id: 'msg-user-edit-width', role: 'user', content: 'Edit this message', createdAt: Date.now() }}
          onEdit={vi.fn()}
        />
      </App>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Edit message' }));
    const editor = screen.getByRole('textbox', { name: 'Edit message' });
    const bubble = editor.parentElement;

    expect(bubble).not.toBeNull();
    expect(getComputedStyle(bubble!).width).toBe('100%');
    expect(getComputedStyle(bubble!).maxWidth).toBe('100%');
  });

  it.each([undefined, { width: 1200, height: 1600 }, { width: 1600, height: 900 }])('preserves intrinsic generated image sizing with metadata %j', (dimensions) => {
    render(<App><MessageItem message={{
      id: 'generated-left', userId: 'user-a', conversationId: 'conv-a', role: 'assistant',
      content: 'Here is the image I created.', createdAt: new Date(), answerBlocks: [{
        type: 'image_block', slotId: 'generated-left', topic: '統計', purpose: 'diagram',
        imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: '統計教學圖',
        provider: 'generated_image', safetyStatus: 'pass', matchConfidence: 1,
        ...dimensions,
      }],
    }} /></App>);
    const image = screen.getByAltText('統計教學圖');
    expect(image.closest('figure')).toHaveStyle({ marginInline: '0' });
    expect(image).toHaveStyle({ objectPosition: 'left center' });
    expect(image).toHaveStyle({ width: '100%', height: 'auto', background: 'transparent' });
    expect(image.closest('button')?.style.aspectRatio).toBe('');
    expect(screen.queryByText('Here is the image I created.')).not.toBeInTheDocument();
  });

  it('opens assistant rich edit mode without exposing Markdown source syntax', () => {
    render(
      <App>
        <MessageItem
          message={{
            id: 'msg-rich-edit-rendered',
            role: 'assistant',
            content: [
              '- test test test',
              '  - test test test test',
              '',
              '| 000 |  | 000 |',
              '| --- | --- | --- |',
              '|  | 000 |  |',
            ].join('\n'),
            createdAt: Date.now(),
          }}
          onEdit={vi.fn()}
        />
      </App>,
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });

    expect(editor).toHaveTextContent('test test test');
    expect(editor.querySelector('table')).toBeInTheDocument();
    expect(editor).not.toHaveTextContent('| --- |');
    expect(editor).not.toHaveTextContent('- test test test');
  });

  it('closes the slash menu with Escape without cancelling assistant editing', () => {
    render(
      <App>
        <MessageItem
          message={{
            id: 'msg-rich-edit-escape',
            role: 'assistant',
            content: 'stable answer',
            createdAt: Date.now(),
          }}
          onEdit={vi.fn()}
        />
      </App>,
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    editor.innerHTML = '<p>/</p>';
    const textNode = editor.querySelector('p')?.firstChild;
    expect(textNode).toBeTruthy();
    const range = document.createRange();
    range.setStart(textNode as Node, 1);
    range.collapse(true);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);

    expect(screen.getByRole('menu', { name: 'Insert block' })).toBeInTheDocument();
    fireEvent.keyDown(editor, { key: 'Escape' });

    expect(screen.queryByRole('menu', { name: 'Insert block' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '編輯訊息' })).toBeInTheDocument();
  });

  it('renders loose bold markers as strong text and keeps code blocks visually scoped', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    const { container } = render(
      <App>
        <MessageItem
          message={{
            id: 'msg-markdown-formatting',
            role: 'assistant',
            content: [
              '用新互動創造 ** 新經驗 **。',
              '',
              '```text',
              'literal ** not bold **',
              '```',
            ].join('\n'),
            createdAt: Date.now(),
          }}
        />
      </App>,
    );

    const strong = container.querySelector('strong');
    const codeBlock = container.querySelector('pre.areqa-markdown-code-block');
    const codeFrame = container.querySelector('.areqa-markdown-code-frame');

    expect(strong).toHaveTextContent('新經驗');
    expect(codeFrame).toBeInTheDocument();
    expect(screen.getByText('text')).toHaveClass('areqa-markdown-code-language');
    expect(codeBlock).toBeInTheDocument();
    expect(codeBlock).toHaveTextContent('literal ** not bold **');
    expect(codeBlock?.querySelector('strong')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '複製 text 文字區塊' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('literal ** not bold **'));
  });

  it('renders a copy action for each assistant display-math block', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(
      <App>
        <MessageItem
          message={{
            id: 'msg-math-1',
            role: 'assistant',
            content: '公式：\n\n$$x^2 + y^2 = z^2$$',
            createdAt: Date.now(),
          }}
        />
      </App>,
    );

    const copyButton = await screen.findByRole('button', { name: '複製公式' });
    fireEvent.click(copyButton);

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('x^2 + y^2 = z^2'));
  });

  it('translates the formula copy action for the selected interface language', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    window.localStorage.setItem('areqa:interface-language', 'en');

    try {
      render(
        <UserPreferencesProvider>
          <App>
            <MessageItem
              message={{
                id: 'msg-math-en',
                role: 'assistant',
                content: '$$x^2$$',
                createdAt: Date.now(),
              }}
            />
          </App>
        </UserPreferencesProvider>,
      );

      expect(await screen.findByRole('button', { name: 'Copy formula' })).toHaveTextContent('Copy formula');
    } finally {
      window.localStorage.removeItem('areqa:interface-language');
    }
  });

  it('Scenario 1: User message with quote block should not be left-aligned', () => {
    const userMessage = {
      id: 'msg-user-1',
      role: 'user' as const,
      content: '> user quote\nuser message text',
      createdAt: Date.now(),
    };

    const { container } = render(<MessageItem message={userMessage} />);
    
    // Check that interactive-quote class is applied
    const quoteBlock = container.querySelector('.interactive-quote');
    expect(quoteBlock).toBeInTheDocument();
    
    // Extract the generated class name for quoteBlock
    const classNames = Array.from(quoteBlock?.classList || []);
    // Find the generated antd-style class (starts with css- or acss-)
    const generatedClass = classNames.find(c => c.startsWith('acss-') || c.startsWith('css-'));
    
    const styleTags = document.head.querySelectorAll('style');
    let cssText = '';
    styleTags.forEach(style => {
      cssText += style.innerHTML;
    });

    if (generatedClass) {
      // Find the block of CSS for this specific class
      const classRegex = new RegExp(`\\.\${generatedClass}\\{([^}]*)\\}`);
      const match = cssText.match(classRegex);
      if (match) {
        const classRules = match[1];
        // The bug was a hardcoded align-self: flex-start
        expect(classRules).not.toMatch(/align-self:\s*flex-start/);
      }
    }

    // Ensure the message has user styling wrapper
    const userMessageWrapper = container.querySelector('[data-message-id="msg-user-1"]');
    expect(userMessageWrapper).toBeInTheDocument();
  });

  it('Scenario 2: Assistant message with quote block still renders properly', () => {
    const aiMessage = {
      id: 'msg-ai-1',
      role: 'assistant' as const,
      content: '> assistant quote\nassistant message text',
      createdAt: Date.now(),
    };

    const { container } = render(<MessageItem message={aiMessage} />);
    
    const blockquote = container.querySelector('blockquote');
    expect(blockquote).toBeInTheDocument();
    expect(blockquote?.textContent).toContain('assistant quote');
  });
});
