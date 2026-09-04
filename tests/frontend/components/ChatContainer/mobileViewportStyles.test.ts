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
    const chatContainerStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/ChatContainer/styles.ts'),
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
    const liveTutorIndex = chatContainer.indexOf('<LiveTutorPanel activeConversationId={activeConversationId} hasMessages={!isEmpty} />');
    const inputAreaIndex = chatContainer.indexOf('areqa-chat-input-area');

    expect(messageAreaIndex).toBeGreaterThan(-1);
    expect(liveTutorIndex).toBeGreaterThan(messageAreaIndex);
    expect(inputAreaIndex).toBeGreaterThan(liveTutorIndex);
    expect(chatContainer).toContain('shouldShowEmptyChat && !isLiveTutorOpen && !gumPanelType');
    expect(liveTutorPanel).not.toContain('className={styles.overlay}');
    expect(liveTutorPanel).toContain('src="/icon/areqa_icon_v4_circle.png"');
    expect(liveTutorPanel).toContain('onInputAudioLevel');
    expect(liveTutorStyles).not.toMatch(/position:\s*fixed;/);
    expect(chatContainer).toContain('areqa-chat-content-live-tutor');
    expect(chatContainer).toContain('areqa-chat-message-area-live-tutor');
    expect(chatContainerStyles).toContain('contentLiveTutor');
    expect(chatContainerStyles).toContain('messageAreaLiveTutor');
    expect(chatContainerStyles).toContain('messageAreaLiveTutorEmpty');
    expect(chatContainer).toContain('!isEmptyLiveTutor && (');
    expect(liveTutorPanel).not.toContain('transcriptText');
    expect(liveTutorPanel).not.toContain('secondaryTranscript');
    expect(liveTutorStyles).toContain('flex: 1 1 auto;');
    expect(liveTutorStyles).toContain('width: clamp(76px, 8vw, 108px);');
    expect(liveTutorStyles).toContain('--live-tutor-audio-scale');
    expect(liveTutorStyles).toContain('scale(var(--live-tutor-audio-scale))');
  });

  it('requests microphone permission before creating a Realtime provider session', () => {
    const realtimeClient = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/services/realtime/client.ts'),
      'utf8',
    );

    const microphoneRequestIndex = realtimeClient.indexOf('navigator.mediaDevices.getUserMedia');
    const sessionRequestIndex = realtimeClient.indexOf('const session = await createRealtimeSession');

    expect(microphoneRequestIndex).toBeGreaterThan(-1);
    expect(sessionRequestIndex).toBeGreaterThan(microphoneRequestIndex);
    expect(realtimeClient).toContain('Microphone permission denied');
    expect(realtimeClient).toContain('microphone_insecure_context');
  });
});
