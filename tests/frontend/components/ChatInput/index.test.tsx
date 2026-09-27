import React from 'react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { render, screen, fireEvent, waitFor, createEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ChatInput } from '@/components/ChatInput';
import { useChatStore } from '@/store/chat';
import { transcribeSpeech } from '@/services/speech/transcription';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';

// Mock Zustand store
vi.mock('@/store/chat', () => ({
  useChatStore: vi.fn(),
}));

vi.mock('@/services/speech/transcription', () => ({
  transcribeSpeech: vi.fn(),
}));

class FakeMediaRecorder {
  static isTypeSupported = vi.fn(() => true);
  state: RecordingState = 'inactive';
  mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(public readonly stream: MediaStream) {}

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['audio'], { type: this.mimeType }) } as BlobEvent);
    this.onstop?.();
  }
}

describe('ChatInput', () => {
  const mockOnSend = vi.fn();
  const mockSetQuotedText = vi.fn();

  it('keeps the input shell layout from animating during initial style overrides', () => {
    const chatInputStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/ChatInput/styles.ts'),
      'utf8',
    );

    const containerRule = chatInputStyles.match(/container:\s*css`(?<rule>[\s\S]*?)`,\n\n\s*containerWithAttachments:/);

    expect(containerRule?.groups?.rule ?? '').toContain('transition: none;');
    expect(containerRule?.groups?.rule ?? '').not.toContain('transition: all');
  });
  const mockToggleWebSearch = vi.fn();
  const mockSetTutorProfile = vi.fn();
  const createObjectUrlMock = vi.fn((file: File) => `blob:${file.name}`);
  const revokeObjectUrlMock = vi.fn();
  const stopTrackMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrlMock,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrlMock,
    });
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    });
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        mediaDevices: {
          getUserMedia: vi.fn(async () => ({
            getTracks: () => [{ stop: stopTrackMock }],
          })),
        },
      },
    });
    vi.mocked(transcribeSpeech).mockResolvedValue('語音輸入完成');
    
    // Default store mock
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        useRag: false,
        useWebSearch: false,
        forceThink: false,
        tutorProfile: 'general',
        quotedText: null,
        toggleRag: vi.fn(),
        toggleWebSearch: mockToggleWebSearch,
        toggleThink: vi.fn(),
        setTutorProfile: mockSetTutorProfile,
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('should render correctly', () => {
    render(<ChatInput onSend={mockOnSend} />);
    expect(screen.getByPlaceholderText(/提問AREQA/i)).toBeDefined();
    expect(screen.getByLabelText('新增')).toBeInTheDocument();
    expect(screen.queryByText('5.5 Medium')).not.toBeInTheDocument();
    expect(screen.queryByText('0/4000')).not.toBeInTheDocument();
    const input = screen.getByLabelText('訊息輸入框');
    const attachmentButton = screen.getByLabelText('新增');
    const webSearchButton = screen.getByLabelText('開啟網路搜尋');
    const inputRow = screen.getByRole('group', { name: '訊息輸入列' });
    const sendButton = screen.getByLabelText('發送訊息');
    expect(inputRow).toContainElement(attachmentButton);
    expect(inputRow).toContainElement(input);
    expect(inputRow).toContainElement(webSearchButton);
    expect(inputRow).toContainElement(sendButton);
    expect(attachmentButton.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(input.compareDocumentPosition(webSearchButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(input.compareDocumentPosition(sendButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('should not focus the composer on initial mount', () => {
    render(<ChatInput onSend={mockOnSend} />);

    expect(screen.getByLabelText('訊息輸入框')).not.toHaveFocus();
  });

  it('should toggle explicit web search from the globe button', () => {
    render(<ChatInput onSend={mockOnSend} />);

    const webSearchButton = screen.getByLabelText('開啟網路搜尋');
    expect(webSearchButton).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(webSearchButton);

    expect(mockToggleWebSearch).toHaveBeenCalledOnce();
  });

  it('should select the English Tutor profile from the add menu', async () => {
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.click(screen.getByLabelText('新增'));
    fireEvent.click(await screen.findByText('English Tutor'));

    expect(mockSetTutorProfile).toHaveBeenCalledWith('english');
  });

  it('should show and clear the active English Tutor profile chip', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        useRag: false,
        useWebSearch: false,
        forceThink: false,
        tutorProfile: 'english',
        quotedText: null,
        toggleRag: vi.fn(),
        toggleWebSearch: mockToggleWebSearch,
        toggleThink: vi.fn(),
        setTutorProfile: mockSetTutorProfile,
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);

    expect(screen.getByText('English Tutor')).toBeInTheDocument();
    expect(screen.getByLabelText('訊息輸入框').closest('.areqa-chat-input-shell-expanded')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('刪除 English Tutor'));

    expect(mockSetTutorProfile).toHaveBeenCalledWith('general');
  });

  it('should keep the send control visibly disabled until there is content', () => {
    render(<ChatInput onSend={mockOnSend} />);
    const sendButton = screen.getByLabelText('發送訊息');

    expect(sendButton).toBeDisabled();
    expect(sendButton.className).toBeTruthy();
  });

  it('should keep the compact pill shell for short single-line text', () => {
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByLabelText('訊息輸入框');

    fireEvent.change(input, { target: { value: 'short question' } });

    expect(input.closest('.areqa-chat-input-shell-expanded')).not.toBeInTheDocument();
  });

  it('should use the attachment-like rounded rectangle shell for long or multiline text', () => {
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByLabelText('訊息輸入框');

    fireEvent.change(input, {
      target: {
        value: 'prompt: combine conversational AI avatars with Socratic tutoring and pedagogical instruction following.',
      },
    });

    expect(input.closest('.areqa-chat-input-shell-expanded')).toBeInTheDocument();
  });

  it('should render a LaTeX preview without changing the submitted source', async () => {
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByPlaceholderText(/提問AREQA/i);

    fireEvent.change(input, { target: { value: '$$x^2 + y^2 = z^2$$' } });

    expect(await screen.findByLabelText('LaTeX 預覽')).toBeInTheDocument();
    expect(screen.getByLabelText('LaTeX 預覽').querySelector('.katex')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));
    expect(mockOnSend).toHaveBeenCalledWith('$$x^2 + y^2 = z^2$$');
  });

  it('should clear the text input immediately while send is still pending', async () => {
    let resolveSend: (value?: void | { completed: boolean }) => void = () => {};
    const pendingSend = vi.fn(() => new Promise<void | { completed: boolean }>((resolve) => {
      resolveSend = resolve;
    }));
    render(<ChatInput onSend={pendingSend} />);
    const input = screen.getByLabelText('訊息輸入框');

    fireEvent.change(input, { target: { value: 'explain this paper' } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    expect(pendingSend).toHaveBeenCalledWith('explain this paper');
    expect(input).toHaveValue('');

    resolveSend({ completed: true });
    await waitFor(() => expect(input).toHaveValue(''));
  });

  it('should show quote preview when quotedText is provided', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'this is a quote',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    expect(screen.getByText('this is a quote')).toBeDefined();
    expect(screen.getByLabelText(/取消引用/i)).toBeDefined();
  });

  it('should call setQuotedText(null) when close button is clicked', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'this is a quote',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    const closeBtn = screen.getByLabelText(/取消引用/i);
    fireEvent.click(closeBtn);
    
    expect(mockSetQuotedText).toHaveBeenCalledWith(null);
  });

  it('should merge quote into message when sending', async () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'quoted content',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByPlaceholderText(/提問AREQA/i);
    
    fireEvent.change(input, { target: { value: 'my question' } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));
    
    expect(mockOnSend).toHaveBeenCalledWith(expect.stringContaining('> quoted content'));
    expect(mockOnSend).toHaveBeenCalledWith(expect.stringContaining('my question'));
    await waitFor(() => expect(mockSetQuotedText).toHaveBeenCalledWith(null));
  });

  it('should send selected attachments with an otherwise empty message', () => {
    const attachment = new File(['notes'], 'notes.md', { type: 'text/markdown' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    expect(screen.getByLabelText('待送附件')).toBeInTheDocument();
    expect(screen.getByTitle('notes.md')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    expect(mockOnSend).toHaveBeenCalledWith('', [attachment]);
  });

  it('should accept txt attachments with a generic browser MIME type', () => {
    const attachment = new File(['script'], 'script.txt', { type: 'application/octet-stream' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    expect(screen.getByTitle('script.txt')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    expect(mockOnSend).toHaveBeenCalledWith('', [attachment]);
  });

  it('should attach pasted images and send them with preview metadata', async () => {
    const pastedImage = new File(['image-data'], 'clipboard.png', { type: 'image/png' });
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByLabelText('訊息輸入框');

    const pasteEvent = createEvent.paste(input);
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => pastedImage,
          },
        ],
      },
    });
    fireEvent(input, pasteEvent);

    expect(await screen.findByTitle(/^pasted-image-.*\.png$/)).toBeInTheDocument();
    expect(screen.getByAltText('圖片附件預覽')).toHaveAttribute('src', expect.stringMatching(/^blob:pasted-image-/));
    expect(screen.getByLabelText('待送附件').closest('.areqa-chat-input-shell-has-attachments')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    await waitFor(() => {
      expect(mockOnSend).toHaveBeenCalledWith(
        '',
        [expect.objectContaining({
          name: expect.stringMatching(/^pasted-image-.*\.png$/),
          type: 'image/png',
        })],
      );
    });
  });

  it('should attach files dropped anywhere in the window', async () => {
    const droppedFile = new File(['notes'], 'dropped-notes.txt', { type: 'text/plain' });
    render(<ChatInput onSend={mockOnSend} />);

    const dragEnterEvent = new Event('dragenter', { bubbles: true, cancelable: true });
    Object.defineProperty(dragEnterEvent, 'dataTransfer', {
      value: { types: ['Files'], files: [droppedFile], dropEffect: 'copy' },
    });
    fireEvent(window, dragEnterEvent);
    expect(screen.getByText('放開即可附加檔案')).toBeInTheDocument();

    const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(dropEvent, 'dataTransfer', {
      value: { types: ['Files'], files: [droppedFile], dropEffect: 'copy' },
    });
    fireEvent(window, dropEvent);

    await waitFor(() => {
      expect(screen.queryByText('放開即可附加檔案')).not.toBeInTheDocument();
      expect(screen.getByTitle('dropped-notes.txt')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));
    expect(mockOnSend).toHaveBeenCalledWith('', [droppedFile]);
  });

  it('should ignore drags that start from components inside the website', () => {
    const draggedFile = new File(['logo'], 'areqa-logo.png', { type: 'image/png' });
    render(
      <>
        <img src="/logo.png" alt="AREQA logo" draggable />
        <ChatInput onSend={mockOnSend} />
      </>,
    );

    fireEvent.dragStart(screen.getByAltText('AREQA logo'));

    const dragEnterEvent = new Event('dragenter', { bubbles: true, cancelable: true });
    Object.defineProperty(dragEnterEvent, 'dataTransfer', {
      value: { types: ['Files'], files: [draggedFile], dropEffect: 'copy' },
    });
    fireEvent(window, dragEnterEvent);

    expect(screen.queryByText('放開即可附加檔案')).not.toBeInTheDocument();

    const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(dropEvent, 'dataTransfer', {
      value: { types: ['Files'], files: [draggedFile], dropEffect: 'copy' },
    });
    fireEvent(window, dropEvent);

    expect(screen.queryByTitle('areqa-logo.png')).not.toBeInTheDocument();
  });

  it('should remove a pending attachment before sending', () => {
    const attachment = new File(['notes'], 'notes.txt', { type: 'text/plain' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByLabelText('刪除 notes.txt'));

    expect(screen.queryByLabelText('待送附件')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/發送訊息/i)).toBeDisabled();
  });

  it('should revoke image preview URLs when image attachments are removed', async () => {
    const attachment = new File(['image'], 'photo.png', { type: 'image/png' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    expect(await screen.findByTitle('photo.png')).toBeInTheDocument();
    expect(screen.getByAltText('圖片附件預覽')).toHaveAttribute('src', 'blob:photo.png');
    fireEvent.click(screen.getByLabelText('刪除 photo.png'));

    await waitFor(() => {
      expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:photo.png');
    });
  });

  it('should preserve draft text and attachments when sending fails', async () => {
    const attachment = new File(['notes'], 'notes.txt', { type: 'text/plain' });
    const failedSend = vi.fn().mockRejectedValue(new Error('network failure'));
    render(<ChatInput onSend={failedSend} />);

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: 'retry this' } });
    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    await waitFor(() => expect(failedSend).toHaveBeenCalledWith('retry this', [attachment]));
    await waitFor(() => expect(screen.getByLabelText('訊息輸入框')).toHaveValue('retry this'));
    expect(screen.getByLabelText('待送附件')).toBeInTheDocument();
  });

  it('should send on Enter but not while an IME composition is active', () => {
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByLabelText('訊息輸入框');

    fireEvent.change(input, { target: { value: 'composed text' } });
    const composingEvent = createEvent.keyDown(input, { key: 'Enter' });
    Object.defineProperty(composingEvent, 'isComposing', { value: true });
    fireEvent(input, composingEvent);
    expect(mockOnSend).not.toHaveBeenCalled();

    const completedEvent = createEvent.keyDown(input, { key: 'Enter' });
    Object.defineProperty(completedEvent, 'isComposing', { value: false });
    fireEvent(input, completedEvent);
    expect(mockOnSend).toHaveBeenCalledWith('composed text');
  });

  it('should show the stop control and call onStop while streaming', () => {
    const onStop = vi.fn();
    render(<ChatInput onSend={mockOnSend} isStreaming onStop={onStop} />);

    expect(screen.queryByLabelText('發送訊息')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('停止生成'));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('should replace the voice and send controls while live voice is active', () => {
    const onToggleLiveVoiceMute = vi.fn();
    const onToggleLiveVoiceAvatar = vi.fn();
    const onCloseLiveVoice = vi.fn();
    render(
      <ChatInput
        onSend={mockOnSend}
        onOpenLiveTutor={vi.fn()}
        isLiveVoiceActive
        isLiveVoiceMuted
        isLiveVoiceAvatarEnabled
        onToggleLiveVoiceMute={onToggleLiveVoiceMute}
        onToggleLiveVoiceAvatar={onToggleLiveVoiceAvatar}
        onCloseLiveVoice={onCloseLiveVoice}
      />,
    );

    expect(screen.queryByLabelText('開啟即時語音')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('發送訊息')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('取消靜音'));
    fireEvent.click(screen.getByLabelText('關閉虛擬角色'));
    fireEvent.click(screen.getByLabelText('結束語音'));
    expect(onToggleLiveVoiceMute).toHaveBeenCalledOnce();
    expect(onToggleLiveVoiceAvatar).toHaveBeenCalledOnce();
    expect(onCloseLiveVoice).toHaveBeenCalledOnce();
  });

  it('sends a selected file while voice remains open', async () => {
    const onCloseLiveVoice = vi.fn();
    const file = new File(['The answer is cobalt.'], 'notes.txt', { type: 'text/plain' });
    render(<ChatInput onSend={mockOnSend} isLiveVoiceActive onCloseLiveVoice={onCloseLiveVoice} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [file] } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(mockOnSend).toHaveBeenCalledWith('', [file]));
    expect(onCloseLiveVoice).not.toHaveBeenCalled();
  });

  it('should show the avatar toggle off state while live voice avatar is disabled', () => {
    const onToggleLiveVoiceAvatar = vi.fn();
    render(
      <ChatInput
        onSend={mockOnSend}
        isLiveVoiceActive
        isLiveVoiceAvatarEnabled={false}
        onToggleLiveVoiceAvatar={onToggleLiveVoiceAvatar}
      />,
    );

    fireEvent.click(screen.getByLabelText('開啟虛擬角色'));

    expect(onToggleLiveVoiceAvatar).toHaveBeenCalledOnce();
  });

  it('should show live voice as the primary action while the composer is empty', () => {
    const onOpenLiveTutor = vi.fn();
    render(<ChatInput onSend={mockOnSend} onOpenLiveTutor={onOpenLiveTutor} />);

    expect(screen.queryByLabelText('發送訊息')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('開啟即時語音'));

    expect(onOpenLiveTutor).toHaveBeenCalledOnce();
  });

  it('should replace live voice with send when the composer has text', () => {
    const onOpenLiveTutor = vi.fn();
    render(<ChatInput onSend={mockOnSend} onOpenLiveTutor={onOpenLiveTutor} />);

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '000' } });

    expect(screen.queryByLabelText('開啟即時語音')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('發送訊息'));
    expect(mockOnSend).toHaveBeenCalledWith('000');
  });

  it('should record speech to text and insert the transcript into the composer', async () => {
    render(<ChatInput onSend={mockOnSend} onOpenLiveTutor={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('語音輸入'));
    expect(await screen.findByLabelText('確認語音輸入')).toBeInTheDocument();
    const waveformBars = document.querySelectorAll('[style*="--wave-level"]');
    expect(waveformBars).toHaveLength(34);
    expect(waveformBars[0]?.getAttribute('style')).not.toContain('--wave-index');
    fireEvent.click(screen.getByLabelText('確認語音輸入'));

    await waitFor(() => {
      expect(transcribeSpeech).toHaveBeenCalledWith(expect.any(Blob), 'zh-TW');
      expect(screen.getByLabelText('訊息輸入框')).toHaveValue('語音輸入完成');
    });
    expect(stopTrackMock).toHaveBeenCalled();
  });

  it('should normalize Chinese dictation to Traditional Chinese when English UI is selected', async () => {
    window.localStorage.setItem('areqa:interface-language', 'en');
    vi.mocked(transcribeSpeech).mockResolvedValue('请解释这篇论文');
    render(
      <UserPreferencesProvider>
        <ChatInput onSend={mockOnSend} onOpenLiveTutor={vi.fn()} />
      </UserPreferencesProvider>,
    );

    fireEvent.click(screen.getByLabelText('Voice dictation'));
    expect(await screen.findByLabelText('Confirm dictation')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Confirm dictation'));

    await waitFor(() => {
      expect(transcribeSpeech).toHaveBeenCalledWith(expect.any(Blob), 'en');
      expect(screen.getByLabelText('Message input')).toHaveValue('請解釋這篇論文');
    });
  });
});
