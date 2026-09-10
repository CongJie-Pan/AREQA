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

  it('uses Times New Roman when the interface language is English', () => {
    const globalsCss = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/app/globals.css'),
      'utf8',
    );

    expect(globalsCss).toMatch(/html\[lang='en'\]\s+body\s*{[^}]*font-family:\s*"Times New Roman",\s*Times,\s*serif;/s);
    expect(globalsCss).toMatch(/html\[lang='en'\]\s+body\s*{[^}]*font-weight:\s*700;/s);
    expect(globalsCss).toMatch(/body\s*{[^}]*font-family:\s*Arial,\s*Helvetica,\s*sans-serif;/s);
  });

  it('hides native WebKit scrollbar arrow buttons and only shows message overflow when needed', () => {
    const globalsCss = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/app/globals.css'),
      'utf8',
    );
    const messageListStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/MessageList/styles.ts'),
      'utf8',
    );

    expect(globalsCss).toMatch(/::-webkit-scrollbar-button\s*{[^}]*display:\s*none;[^}]*width:\s*0;[^}]*height:\s*0;/s);
    expect(messageListStyles).toMatch(/container:\s*css`[^`]*overflow-y:\s*auto;/s);
    expect(messageListStyles).not.toContain('overflow-y: scroll;');
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
    const liveTutorAvatarStage = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/LiveTutor/LiveTutorAvatarStage.tsx'),
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
    expect(liveTutorPanel).toContain('<LiveTutorAvatarStage');
    expect(liveTutorAvatarStage).toContain('src="/icon/areqa_icon_v4_circle.png"');
    expect(liveTutorAvatarStage).toContain('avatarEnabled');
    expect(liveTutorAvatarStage).toContain('<video');
    expect(liveTutorPanel).toContain('onInputAudioLevel');
    expect(liveTutorPanel).toContain("layout === 'inline' && isAvatarVideoReady && avatarVideoStream && !error");
    expect(chatContainer).toContain('areqa-chat-content-live-tutor');
    expect(chatContainer).toContain('areqa-chat-message-area-live-tutor');
    expect(chatContainerStyles).toContain('contentLiveTutor');
    expect(chatContainerStyles).toContain('messageAreaLiveTutor');
    expect(chatContainerStyles).toContain('messageAreaLiveTutorEmpty');
    expect(chatContainer).toContain('!isEmptyLiveTutor && (');
    expect(liveTutorPanel).not.toContain('transcriptText');
    expect(liveTutorPanel).not.toContain('secondaryTranscript');
    expect(liveTutorStyles).toContain('flex: 1 1 auto;');
    expect(liveTutorStyles).toContain('background: transparent;');
    expect(liveTutorStyles).toContain('align-items: center;');
    expect(liveTutorStyles).toContain('justify-content: center;');
    expect(liveTutorStyles).toContain('width: min(100%, 292px);');
    expect(liveTutorStyles).toContain('height: min(calc(100% - 28px), 560px);');
    expect(liveTutorStyles).toContain('width: clamp(78px, 8vw, 104px);');
    expect(liveTutorStyles).not.toContain('logoOrbActive');
    expect(liveTutorPanel).not.toContain('statusLabels');
    expect(liveTutorPanel).not.toContain('styles.controlCluster');
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
