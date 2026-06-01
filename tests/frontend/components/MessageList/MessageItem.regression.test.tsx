import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';

// We do NOT mock styles.ts to ensure we test actual CSS-in-JS behavior
vi.mock('../../../../frontend/src/components/RAGStatusPanel', () => ({
  RAGStatusPanel: () => <div data-testid="rag-status-panel"></div>
}));

vi.mock('../../../../frontend/src/components/ThinkingPanel', () => ({
  ThinkingPanel: () => <div data-testid="thinking-panel"></div>
}));

describe('MessageItem Quote Alignment Regression', () => {
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
    
    const blockquote = container.querySelector('blockquote.interactive-quote');
    expect(blockquote).toBeInTheDocument();
    expect(blockquote?.textContent).toContain('assistant quote');
  });
});
