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
  it('renders loose bold markers as strong text and keeps code blocks visually scoped', () => {
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

    expect(strong).toHaveTextContent('新經驗');
    expect(codeBlock).toBeInTheDocument();
    expect(codeBlock).toHaveTextContent('literal ** not bold **');
    expect(codeBlock?.querySelector('strong')).not.toBeInTheDocument();
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
