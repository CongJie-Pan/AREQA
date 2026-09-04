import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('ChatContainer mobile viewport styles', () => {
  it('anchors the chat shell at the layout viewport top while visualViewport height changes', () => {
    const globalsCss = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/app/globals.css'),
      'utf8',
    );
    const chatContainerStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/ChatContainer/styles.ts'),
      'utf8',
    );

    expect(globalsCss).toMatch(/\.areqa-chat-shell\s*{[^}]*top:\s*0;/s);
    expect(chatContainerStyles).toMatch(/container:\s*css`[^`]*top:\s*0;/s);
    expect(chatContainerStyles).toContain('height: var(--areqa-visual-viewport-height, 100dvh);');
  });

  it('renders Live Tutor inline between messages and the normal input bar', () => {
    const chatContainer = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/ChatContainer/index.tsx'),
      'utf8',
    );
    const liveTutorPanel = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/LiveTutor/LiveTutorPanel.tsx'),
      'utf8',
    );
    const liveTutorStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/LiveTutor/styles.ts'),
      'utf8',
    );

    const messageAreaIndex = chatContainer.indexOf('areqa-chat-message-area');
    const liveTutorIndex = chatContainer.indexOf('<LiveTutorPanel activeConversationId={activeConversationId} />');
    const inputAreaIndex = chatContainer.indexOf('areqa-chat-input-area');

    expect(messageAreaIndex).toBeGreaterThan(-1);
    expect(liveTutorIndex).toBeGreaterThan(messageAreaIndex);
    expect(inputAreaIndex).toBeGreaterThan(liveTutorIndex);
    expect(liveTutorPanel).not.toContain('className={styles.overlay}');
    expect(liveTutorPanel).toContain('src="/icon/areqa_icon_v4_circle.png"');
    expect(liveTutorPanel).toContain('onInputAudioLevel');
    expect(liveTutorStyles).not.toMatch(/position:\s*fixed;/);
    expect(liveTutorStyles).toContain('flex: 0 0 auto;');
    expect(liveTutorStyles).toContain('--live-tutor-audio-scale');
    expect(liveTutorStyles).toContain('scale(var(--live-tutor-audio-scale))');
  });
});
