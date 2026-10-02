import React from 'react';
import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import { createReadAloudAudio } from '../../../../frontend/src/services/speech/readAloud';
import { authenticatedFetch } from '@/services/authenticatedFetch';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));

// Mock child components to isolate tests
vi.mock('../../../../frontend/src/components/RAGStatusPanel', () => ({
  RAGStatusPanel: ({ ragInfo }: any) => (
    <div data-testid="rag-status-panel">{ragInfo.message}</div>
  )
}));

vi.mock('../../../../frontend/src/components/MessageList/styles', () => ({
  useStyles: () => ({
    styles: { 
      assistantMessageWrapper: 'assistantMessageWrapper', 
      assistantBubble: 'assistantBubble',
      assistantBubbleReveal: 'assistantBubbleReveal',
      actionButtons: 'actionButtons',
      actionButton: 'actionButton',
      bubble: 'bubble',
      userBubble: 'userBubble',
      bubbleWrapper: 'bubbleWrapper',
      messageAttachmentList: 'messageAttachmentList',
      messageAttachmentCard: 'messageAttachmentCard',
      messageAttachmentIcon: 'messageAttachmentIcon',
      messageAttachmentDetails: 'messageAttachmentDetails',
      messageAttachmentName: 'messageAttachmentName',
      messageAttachmentMeta: 'messageAttachmentMeta',
      messageAttachmentToggleWrap: 'messageAttachmentToggleWrap',
      messageAttachmentToggle: 'messageAttachmentToggle',
      messageAttachmentToggleIcon: 'messageAttachmentToggleIcon',
      messageAttachmentToggleChevron: 'messageAttachmentToggleChevron',
      messageAttachmentToggleChevronOpen: 'messageAttachmentToggleChevronOpen',
      messageAttachmentPopoverContainer: 'messageAttachmentPopoverContainer',
      messageAttachmentDropdown: 'messageAttachmentDropdown',
      messageAttachmentDropdownItem: 'messageAttachmentDropdownItem',
      messageAttachmentDropdownIcon: 'messageAttachmentDropdownIcon',
      messageAttachmentDropdownName: 'messageAttachmentDropdownName',
      answerImageCard: 'answerImageCard',
      generatedImageCard: 'generatedImageCard',
      answerImageExplanation: 'answerImageExplanation',
      answerImageButton: 'answerImageButton',
      answerImageSkeleton: 'answerImageSkeleton',
      answerImage: 'answerImage',
      answerImageCaption: 'answerImageCaption',
      answerImageCaptionText: 'answerImageCaptionText',
      answerImageMetaLine: 'answerImageMetaLine',
      answerImageLicense: 'answerImageLicense',
      answerImageSource: 'answerImageSource',
      answerImageLightbox: 'answerImageLightbox',
      answerImageLightboxDownload: 'answerImageLightboxDownload',
      answerImageLightboxBody: 'answerImageLightboxBody',
      answerImageLightboxImage: 'answerImageLightboxImage',
      answerImageLightboxMeta: 'answerImageLightboxMeta',
      answerImageLightboxSource: 'answerImageLightboxSource',
      content: 'content',
      streamingDots: 'streamingDots',
      streamingDot: 'streamingDot',
      actionButtonActive: 'actionButtonActive',
      feedbackActionSlot: 'feedbackActionSlot',
      feedbackActionSlotCollapsed: 'feedbackActionSlotCollapsed',
      editModeContainer: 'editModeContainer',
      editTextarea: 'editTextarea',
      assistantEditSurface: 'assistantEditSurface',
      richEditSurface: 'richEditSurface',
      richEditSlashMenu: 'richEditSlashMenu',
      richEditSlashMenuItem: 'richEditSlashMenuItem',
      editButtons: 'editButtons',
      editButton: 'editButton',
      editCancelButton: 'editCancelButton',
      editSaveButton: 'editSaveButton',
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

// Mock markdown component
vi.mock('react-markdown', () => ({
  default: ({ children }: any) => <div>{children}</div>
}));

vi.mock('../../../../frontend/src/services/speech/readAloud', async () => {
  const actual = await vi.importActual<typeof import('../../../../frontend/src/services/speech/readAloud')>(
    '../../../../frontend/src/services/speech/readAloud',
  );
  return {
    ...actual,
    createReadAloudAudio: vi.fn(),
  };
});

class MockAudio {
  static instances: MockAudio[] = [];
  src: string;
  listeners: Record<string, EventListenerOrEventListenerObject[]> = {};
  play = vi.fn().mockResolvedValue(undefined);
  pause = vi.fn();

  constructor(src: string) {
    this.src = src;
    MockAudio.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners[type] = [...(this.listeners[type] ?? []), listener];
  }
}

describe('MessageItem Integration with RAGStatusPanel', () => {
  const baseMessage = {
    id: 'msg-1',
    role: 'assistant' as const,
    content: '這是測試訊息',
    createdAt: Date.now(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    MockAudio.instances = [];
    vi.stubGlobal('Audio', MockAudio as any);
    Object.defineProperty(window, 'Audio', {
      configurable: true,
      value: MockAudio,
    });
    global.URL.createObjectURL = vi.fn(() => 'blob:read-aloud');
    global.URL.revokeObjectURL = vi.fn();
    vi.mocked(createReadAloudAudio).mockResolvedValue(new Blob(['audio'], { type: 'audio/mpeg' }));
  });

  it('Scenario 1: Render RAGStatusPanel when active', () => {
    const emptyMessage = { ...baseMessage, content: '' };
    const ragInfo = {
      status: 'searching_dense' as const,
      message: '檢索中...',
      sources: [],
    };
    
    render(
      <MessageItem 
        message={emptyMessage} 
        isStreaming={true} 
        ragInfo={ragInfo} 
      />
    );
    
    const panel = screen.getByTestId('rag-status-panel');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent('檢索中...');
  });

  it('Scenario 2: Do not render RAGStatusPanel when idle', () => {
    const ragInfo = {
      status: 'idle' as const,
      message: '',
      sources: [],
    };
    
    render(
      <MessageItem 
        message={baseMessage} 
        isStreaming={true} 
        ragInfo={ragInfo} 
      />
    );
    
    expect(screen.queryByTestId('rag-status-panel')).not.toBeInTheDocument();
  });

  it('calls the latest-turn delete callback from the assistant action row', () => {
    const onDeleteLatestTurn = vi.fn();

    render(
      <MessageItem
        message={baseMessage}
        isLast
        onDeleteLatestTurn={onDeleteLatestTurn}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '刪除對話' }));

    expect(onDeleteLatestTurn).toHaveBeenCalledWith('msg-1');
  });

  it('calls the add-note callback from the assistant action row', () => {
    const onAddNote = vi.fn();

    render(
      <MessageItem
        message={baseMessage}
        onAddNote={onAddNote}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '加入筆記' }));

    expect(onAddNote).toHaveBeenCalledWith('msg-1');
  });

  it('shows an inactive saved-note action when the assistant reply is already saved', () => {
    const onAddNote = vi.fn();

    render(
      <MessageItem
        message={baseMessage}
        isSavedNote
        onAddNote={onAddNote}
      />
    );

    const button = screen.getByRole('button', { name: '已在筆記中' });
    expect(button).toBeDisabled();

    fireEvent.click(button);

    expect(onAddNote).not.toHaveBeenCalled();
  });

  it('lets completed assistant replies be edited in a rich rendered surface', async () => {
    const onEdit = vi.fn();

    render(
      <MessageItem
        message={{ ...baseMessage, content: 'old **answer**' }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    expect(editor).toHaveTextContent('old answer');
    expect(editor.closest('.assistantBubble')).not.toBeNull();
    expect(editor.closest('.assistantEditSurface')).not.toBeNull();
    expect(editor.closest('.richEditSurface')).not.toBeNull();

    editor.innerHTML = '<p>new <img alt="圖" src="https://example.com/image.png"></p>';
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', 'new ![圖](https://example.com/image.png)');
    });
  });

  it('preserves rich assistant markdown when editing rendered content', async () => {
    const onEdit = vi.fn();
    const richContent = [
      '- parent',
      '  - child',
      '',
      '| A\\|B | C |',
      '| --- | --- |',
      '| 1 | 2 |',
      '|  |  |',
      '',
      '> **important** [link](https://example.com/?a=1&b=2)',
      '',
      '```js',
      'const foo_bar_baz = 1;',
      '```',
    ].join('\n');

    render(
      <MessageItem
        message={{ ...baseMessage, content: richContent }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    expect(editor).toHaveTextContent('parent');
    expect(editor).toHaveTextContent('child');
    expect(editor).toHaveTextContent('A|B');
    expect(editor).not.toHaveTextContent('```js');

    editor.insertAdjacentHTML('beforeend', '<p>tail</p>');
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', [
        '- parent',
        '  - child',
        '',
        '| A\\|B | C |',
        '| --- | --- |',
        '| 1 | 2 |',
        '|  |  |',
        '',
        '> **important** [link](https://example.com/?a=1&b=2)',
        '',
        '```js',
        'const foo_bar_baz = 1;',
        '```',
        '',
        'tail',
      ].join('\n'));
    });
  });

  it('keeps list markdown after saving wrapped assistant editor content and reopening edit', async () => {
    let savedContent = '- old';
    const onEdit = vi.fn(async (_id: string, nextContent: string) => {
      savedContent = nextContent;
    });
    const { rerender } = render(
      <MessageItem
        message={{ ...baseMessage, content: savedContent }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    editor.innerHTML = '<div><ul><li data-depth="0">test</li></ul></div>';
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', '- test');
    });

    rerender(
      <MessageItem
        message={{ ...baseMessage, content: savedContent }}
        onEdit={onEdit}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));

    const reopenedEditor = screen.getByRole('textbox', { name: '編輯訊息' });
    expect(reopenedEditor.querySelector('ul li')).toHaveTextContent('test');
    expect(reopenedEditor).not.toHaveTextContent('- test');
  });

  it('inserts slash command blocks at the current assistant edit caret', async () => {
    const onEdit = vi.fn();

    render(
      <MessageItem
        message={{ ...baseMessage, content: 'intro' }}
        onEdit={onEdit}
      />
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

    fireEvent.click(screen.getByRole('menuitem', { name: /Table/ }));
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', [
        '| 欄位 A | 欄位 B | 欄位 C |',
        '| --- | --- | --- |',
        '| 內容 |  | 內容 |',
        '|  | 內容 |  |',
      ].join('\n'));
    });
  });

  it('inserts a pasted image into assistant edit markdown', async () => {
    const onEdit = vi.fn();
    class MockFileReader {
      result: string | ArrayBuffer | null = null;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      readAsDataURL() {
        this.result = 'data:image/png;base64,abc123';
        this.onload?.();
      }
    }
    vi.stubGlobal('FileReader', MockFileReader as any);

    render(
      <MessageItem
        message={{ ...baseMessage, content: 'old answer' }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    fireEvent.paste(editor, {
      clipboardData: {
        files: [
          new File(['tiny'], 'diagram.png', { type: 'image/png' }),
        ],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', 'old answer\n\n![diagram.png](data:image/png;base64,abc123)');
    });
  });

  it('keeps the assistant edit draft open when saving fails', async () => {
    const onEdit = vi.fn().mockRejectedValue(new Error('save failed'));

    render(
      <MessageItem
        message={{ ...baseMessage, content: 'old answer' }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    editor.innerHTML = '<p>draft answer</p>';
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(onEdit).toHaveBeenCalledWith('msg-1', 'draft answer');
    });
    expect(screen.getByRole('textbox', { name: '編輯訊息' })).toHaveTextContent('draft answer');
  });

  it('keeps user attachments visible while editing and exits edit mode immediately on submit', async () => {
    let resolveEdit: (() => void) | undefined;
    const onEdit = vi.fn(() => new Promise<void>((resolve) => {
      resolveEdit = resolve;
    }));

    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: 'old question',
          attachments: [{ name: 'diagram.png', mediaType: 'image/png', sizeBytes: 2048 }],
        }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    expect(editor.closest('.userBubble')).not.toBeNull();
    expect(screen.getByLabelText('附件 diagram.png')).toBeInTheDocument();

    fireEvent.change(editor, { target: { value: 'edited question' } });
    fireEvent.click(screen.getByRole('button', { name: '送出' }));

    await waitFor(() => {
      expect(screen.queryByRole('textbox', { name: '編輯訊息' })).not.toBeInTheDocument();
    });
    expect(onEdit).toHaveBeenCalledWith('msg-1', 'edited question');

    await act(async () => {
      resolveEdit?.();
    });
  });

  it('cancels assistant reply editing without saving changes', () => {
    const onEdit = vi.fn();

    render(
      <MessageItem
        message={{ ...baseMessage, content: 'stable answer' }}
        onEdit={onEdit}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });
    editor.innerHTML = '<p>discarded answer</p>';
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox', { name: '編輯訊息' })).not.toBeInTheDocument();
  });

  it('reads an assistant reply aloud from the action row', async () => {
    render(
      <UserPreferencesProvider>
        <App>
          <MessageItem message={{ ...baseMessage, content: '**重點**：請慢慢讀。' }} />
        </App>
      </UserPreferencesProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: '朗讀回覆' }));

    expect(createReadAloudAudio).toHaveBeenCalledWith('重點：請慢慢讀。', expect.any(AbortSignal));
    expect(await screen.findByRole('button', { name: '停止朗讀' })).toHaveAttribute('aria-pressed', 'true');
    expect(MockAudio.instances[0]?.src).toBe('blob:read-aloud');
    expect(MockAudio.instances[0]?.play).toHaveBeenCalled();
  });

  it('renders persisted user attachment metadata below the message text', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請解釋這份 PDF',
          attachments: [{ name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 }],
        }}
      />
    );

    expect(screen.getByText('請解釋這份 PDF')).toBeInTheDocument();
    expect(screen.getByLabelText('附件 lesson.pdf')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByLabelText('1 個附件').closest('.userBubble')).not.toBeInTheDocument();
  });

  it('hides the legacy attachment marker and renders a compatibility card', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請解釋這份 PDF\n\n[已附加 1 個檔案]',
        }}
      />
    );

    expect(screen.queryByText(/已附加 1 個檔案/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('附件 附件 1')).toBeInTheDocument();
  });

  it('renders quote-branch attachments outside the user bubble', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '> 原始問題\n\n請解釋這份 PDF',
          attachments: [{ name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 }],
        }}
      />
    );

    expect(screen.getByLabelText('1 個附件').closest('.userBubble')).not.toBeInTheDocument();
    expect(screen.getByText('原始問題')).toBeInTheDocument();
    expect(screen.getByText('請解釋這份 PDF')).toBeInTheDocument();
  });

  it('collapses multiple attachments into an expandable filename list', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請幫我確認',
          attachments: [
            { name: 'first.pdf', mediaType: 'application/pdf', sizeBytes: 2048 },
            { name: 'second.pdf', mediaType: 'application/pdf', sizeBytes: 4096 },
          ],
        }}
      />
    );

    const toggle = screen.getByRole('button', { name: /2 個附件/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('附件清單')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('附件 first.pdf')).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const attachmentList = screen.getByLabelText('附件清單');
    expect(attachmentList).toBeInTheDocument();
    expect(attachmentList.closest('.messageAttachmentList')).toBeNull();
    expect(screen.getByText('first.pdf')).toBeInTheDocument();
    expect(screen.getByText('second.pdf')).toBeInTheDocument();
  });

  it('localizes the collapsed attachment count', () => {
    window.localStorage.setItem('areqa:interface-language', 'en');

    render(
      <UserPreferencesProvider>
        <MessageItem
          message={{
            ...baseMessage,
            role: 'user',
            content: 'Please compare these files',
            attachments: [
              { name: 'first.pdf', mediaType: 'application/pdf', sizeBytes: 2048 },
              { name: 'second.pdf', mediaType: 'application/pdf', sizeBytes: 4096 },
            ],
          }}
        />
      </UserPreferencesProvider>
    );

    expect(screen.getByRole('button', { name: /2 attachments/ })).toBeInTheDocument();
    expect(screen.getByLabelText('2 attachments')).toBeInTheDocument();
  });

  it('renders illustrated answer blocks inline and opens a lightbox', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          content: 'fallback text',
          answerBlocks: [
            { type: 'paragraph', text: '第一段' },
            {
              type: 'image_block',
              slotId: 'visual-1',
              topic: 'Forest plot',
              purpose: 'diagram',
              imageUrl: 'https://example.com/forest.png',
              sourceUrl: 'https://example.com/article',
              sourceDomain: 'example.com',
              caption: 'Forest plot example',
              provider: 'wikimedia',
              license: 'CC BY-SA 4.0',
              licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
              creator: 'Example Creator',
              attributionString: 'Example Creator / CC BY-SA 4.0',
              attributionCaption: 'Forest plot example',
              explanatoryCaption: '這張森林圖可以這樣看。',
              safetyStatus: 'pass',
              matchConfidence: 0.6,
            },
            { type: 'paragraph', text: '第二段' },
          ],
        }}
      />
    );

    expect(screen.getByText('第一段')).toBeInTheDocument();
    expect(screen.getByText('這張森林圖可以這樣看。')).toBeInTheDocument();
    expect(screen.getByAltText('Forest plot example')).toHaveAttribute(
      'src',
      'https://example.com/forest.png',
    );
    expect(screen.getByRole('button', { name: /放大檢視圖片/ })).toBeInTheDocument();
    expect(screen.getByText('來源')).toHaveAttribute('href', 'https://example.com/article');
    expect(screen.queryByText('CC BY-SA 4.0')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /放大檢視圖片/ }));

    expect(screen.getByText('開啟原始來源')).toHaveAttribute('href', 'https://example.com/article');
    expect(screen.getByText(/Example Creator \/ CC BY-SA 4.0/)).toBeInTheDocument();
    expect(screen.queryByText('License:')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'CC BY-SA 4.0' })).not.toBeInTheDocument();
    expect(screen.getByText('第二段')).toBeInTheDocument();
    expect(screen.queryByText('fallback text')).not.toBeInTheDocument();
  });

  it('renders pending planned image blocks as an inline skeleton', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          content: 'fallback text',
          answerBlocks: [
            { type: 'paragraph', text: '第一段' },
            {
              type: 'image_block',
              slotId: 'img-1',
              topic: 'Visual aid',
              purpose: 'diagram',
              imageUrl: '',
              sourceUrl: '',
              sourceDomain: '',
              caption: '正在找概念圖',
              status: 'pending',
              safetyStatus: 'unavailable',
              matchConfidence: 0,
            },
            { type: 'paragraph', text: '第二段' },
          ],
        }}
      />
    );

    expect(screen.getByText('第一段')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '圖片搜尋中' })).toBeInTheDocument();
    expect(screen.getByText('正在找概念圖')).toBeInTheDocument();
    expect(screen.getByText('第二段')).toBeInTheDocument();
    expect(screen.queryByText('fallback text')).not.toBeInTheDocument();
  });

  it('renders generated images without a model label or fabricated source link', () => {
    render(
      <MessageItem message={{
        ...baseMessage,
        answerBlocks: [{
          type: 'image_block', slotId: 'generated-1', topic: '細胞', purpose: 'diagram',
          imageUrl: 'https://example.com/generated.png', sourceUrl: '', sourceDomain: '',
          caption: '細胞結構', attributionCaption: '請畫細胞結構', explanatoryCaption: '請畫細胞結構',
          provider: 'generated_image', model: 'qwen/qwen-image-3-pro',
          safetyStatus: 'pass', matchConfidence: 1,
        }],
      }} />,
    );
    expect(screen.getByAltText('請畫細胞結構')).toHaveAttribute('src', 'https://example.com/generated.png');
    expect(screen.getByAltText('請畫細胞結構').closest('figure')).toHaveClass('generatedImageCard');
    expect(screen.queryByText('請畫細胞結構')).not.toBeInTheDocument();
    expect(screen.queryByText('AI 生成')).not.toBeInTheDocument();
    expect(screen.queryByText('qwen/qwen-image-3-pro')).not.toBeInTheDocument();
    expect(screen.queryByText('來源')).not.toBeInTheDocument();
    fireEvent.click(screen.getByAltText('請畫細胞結構').closest('button')!);
    expect(screen.queryByText('請畫細胞結構')).not.toBeInTheDocument();
    expect(screen.queryByText('qwen/qwen-image-3-pro')).not.toBeInTheDocument();
    expect(screen.queryByText('AI 生成')).not.toBeInTheDocument();
    const download = screen.getByRole('link', { name: '下載圖片' });
    expect(download).toHaveClass('answerImageLightboxDownload');
    expect(download.nextElementSibling).toHaveAttribute('aria-label', '關閉圖片檢視');
  });

  it('shows pending generation and hides regenerate until the image completes', () => {
    render(<MessageItem onRegenerate={vi.fn()} onDeleteLatestTurn={vi.fn()} message={{
      ...baseMessage, isStreaming: false, content: '', answerBlocks: [{
        type: 'image_block', slotId: 'pending-a', topic: '圖', purpose: 'diagram',
        imageUrl: '', sourceUrl: '', sourceDomain: '', caption: '正在產生圖片…',
        provider: 'generated_image', status: 'pending', safetyStatus: 'pass', matchConfidence: 1,
      }],
    }} />);
    expect(screen.getByText('正在產生圖片…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新生成訊息' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '刪除對話' })).not.toBeInTheDocument();
    expect(screen.getByText('你可以隨時停止生成。')).toBeInTheDocument();
    expect(screen.getByTestId('answer-image-skeleton')).toBeInTheDocument();
    expect(screen.getByTestId('answer-image-skeleton').closest('figure')).toHaveClass('generatedImageCard');
  });

  it.each(['Here is the image I created.', '這是為你產生的圖片。'])(
    'hides legacy completion text when reopening an image reply (%s)', (content) => {
      render(<MessageItem message={{ ...baseMessage, content, answerBlocks: [{
        type: 'image_block', slotId: 'legacy-image', topic: '統計', purpose: 'diagram',
        imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: '統計教學图',
        provider: 'generated_image', status: 'resolved', safetyStatus: 'pass', matchConfidence: 1,
      }] }} />);
      expect(screen.queryByText(content)).not.toBeInTheDocument();
      expect(screen.getByAltText('統計教學图')).toBeInTheDocument();
    },
  );

  it('keeps download warnings visible for generated images that could not be saved', () => {
    const content = 'The image is ready, but could not be saved. Please download it now.';
    render(<MessageItem message={{ ...baseMessage, content, answerBlocks: [{
      type: 'image_block', slotId: 'unsaved-image', topic: '統計', purpose: 'diagram',
      imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: '統計教學圖',
      provider: 'generated_image', status: 'resolved', safetyStatus: 'pass', matchConfidence: 1,
    }] }} />);
    expect(screen.getByText(content)).toBeInTheDocument();
  });

  it('shows an image load error and renews the stored URL when retrying', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ imageUrl: 'https://example.test/renewed.png' })));
    render(<MessageItem message={{ ...baseMessage, conversationId: 'conv-a', answerBlocks: [{
      type: 'image_block', slotId: 'image-a', topic: '圖', purpose: 'diagram',
      imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: '解說圖',
      provider: 'generated_image', status: 'resolved', safetyStatus: 'pass', matchConfidence: 1,
      storagePath: 'users/owner/image.png', storageExpiresAt: Math.floor(Date.now() / 1000) + 3600,
    }] }} />);
    fireEvent.error(screen.getByAltText('解說圖'));
    expect(screen.getByText('圖片載入失敗。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新載入圖片' }));
    await waitFor(() => expect(screen.getByAltText('解說圖')).toHaveAttribute('src', 'https://example.test/renewed.png'));
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/images/refresh', expect.objectContaining({ method: 'POST' }));
  });

  it('renders a failed image request visibly and keeps its regenerate action', () => {
    render(<MessageItem onRegenerate={vi.fn()} message={{ ...baseMessage, content: '', answerBlocks: [{
      type: 'image_block', slotId: 'error-a', topic: '圖', purpose: 'diagram', imageUrl: '',
      sourceUrl: '', sourceDomain: '', caption: '目前無法產生圖片，請稍後重試。',
      provider: 'generated_image', status: 'error', safetyStatus: 'pass', matchConfidence: 1,
    }] }} />);
    expect(screen.getByText('目前無法產生圖片，請稍後重試。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新生成訊息' })).toBeInTheDocument();
  });

  it('renews an expired generated image URL when reopening a conversation', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({
      imageUrl: 'https://example.com/renewed.png', storageExpiresAt: Math.floor(Date.now() / 1000) + 3600,
    })));
    render(<MessageItem message={{
      ...baseMessage, conversationId: 'conv-a',
      answerBlocks: [{
        type: 'image_block', slotId: 'image-a', topic: '細胞', purpose: 'diagram',
        imageUrl: 'https://example.com/expired.png', sourceUrl: '', sourceDomain: '',
        caption: '細胞結構', provider: 'generated_image', safetyStatus: 'pass', matchConfidence: 1,
        storagePath: 'users/owner/conversations/conv-a/generated-images/image-a.png',
        storageExpiresAt: Math.floor(Date.now() / 1000) - 10,
      }],
    }} />);

    await waitFor(() => expect(screen.getByAltText('細胞結構')).toHaveAttribute('src', 'https://example.com/renewed.png'));
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/images/refresh', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ conversation_id: 'conv-a', image_id: 'image-a' }),
    }));
  });

  it('downloads a private generated image through the authenticated proxy', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(new Blob(['png'], { type: 'image/png' })));
    const linkClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<MessageItem message={{
      ...baseMessage, conversationId: 'conv-a',
      answerBlocks: [{
        type: 'image_block', slotId: 'image-a', topic: '細胞', purpose: 'diagram',
        imageUrl: 'https://example.com/image.png', sourceUrl: '', sourceDomain: '',
        caption: '細胞圖', provider: 'generated_image', safetyStatus: 'pass', matchConfidence: 1,
        storagePath: 'users/owner/conversations/conv-a/generated-images/image-a.png',
        storageExpiresAt: Math.floor(Date.now() / 1000) + 3600,
      }],
    }} />);
    fireEvent.click(screen.getByAltText('細胞圖').closest('button')!);
    fireEvent.click(screen.getByRole('link', { name: '下載圖片' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledWith('/api/images/download', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ conversation_id: 'conv-a', image_id: 'image-a' }),
    })));
    await waitFor(() => expect(linkClick).toHaveBeenCalled());
    linkClick.mockRestore();
  });

  it('uses a container-level reveal for streaming assistant markdown', () => {
    const { container } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '串流動畫測試',
        }}
        isStreaming={true}
      />
    );

    expect(container).toHaveTextContent('串流動畫測試');
    expect(container.querySelector('[data-streaming-content="true"]')).toBeInTheDocument();
    expect(container.querySelector('[data-sd-animate]')).toBeInTheDocument();
    expect(container.querySelector('.streamingDots')).toBeInTheDocument();
    expect(container.querySelectorAll('.streamingDot')).toHaveLength(3);
    expect(container.querySelector('.streamingCursor')).not.toBeInTheDocument();
  });

  it('renders single-dollar inline math in assistant messages', () => {
    const { container } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '角度是 $\\theta$',
        }}
      />
    );

    expect(container.querySelector('.katex')).toBeInTheDocument();
    expect(container.querySelector('annotation')).toHaveTextContent('\\theta');
  });

  it('renders Markdown tables with floating copy, CSV download, and expand actions', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const createObjectURL = vi.fn(() => 'blob:table-csv');
    const revokeObjectURL = vi.fn();
    const anchorClick = vi
      .spyOn(window.HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
    });

    const { container } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '| 名稱 | 數值 |\n| --- | --- |\n| theta | 42 |',
        }}
      />
    );

    const frame = container.querySelector('.areqa-markdown-table-frame');
    const scrollRegion = screen.getByLabelText('可水平捲動的資料表');
    const copyButton = screen.getByRole('button', { name: '複製表格' });
    const downloadButton = screen.getByRole('button', { name: '下載表格為CSV' });
    const expandButton = screen.getByRole('button', { name: '擴大顯示表格' });
    expect(frame).toBeInTheDocument();
    expect(scrollRegion).toHaveClass('areqa-markdown-table-scroll');
    expect(scrollRegion).toHaveAttribute('tabindex', '0');
    expect(scrollRegion.querySelector('table')).toHaveClass('areqa-markdown-table');
    expect(copyButton).toHaveClass('areqa-markdown-table-action');
    expect(downloadButton).toHaveClass('areqa-markdown-table-action');
    expect(expandButton).toHaveClass('areqa-markdown-table-action');
    expect(screen.getByRole('columnheader', { name: '名稱' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '42' })).toBeInTheDocument();
    expect(container.querySelector('[data-streamdown="table-wrapper"]')).not.toBeInTheDocument();

    fireEvent.click(copyButton);
    expect(writeText).toHaveBeenCalledWith('名稱\t數值\ntheta\t42');

    fireEvent.click(downloadButton);
    expect(anchorClick).toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:table-csv');

    fireEvent.click(expandButton);
    const dialog = screen.getByRole('dialog', { name: '表格' });
    expect(dialog).toBeInTheDocument();
    expect(container.querySelector('.areqa-markdown-table-modal-backdrop')).not.toBeInTheDocument();
    expect(document.body.querySelector('.areqa-markdown-table-modal-backdrop')).toBe(dialog);
    expect(document.body.style.overflow).toBe('hidden');
    expect(screen.getByRole('heading', { name: '表格' })).toBeInTheDocument();
    const modalBody = document.body.querySelector('.areqa-markdown-table-modal-body');
    expect(modalBody).toBeInTheDocument();
    expect(modalBody?.querySelector('table')).toHaveClass('areqa-markdown-table');

    fireEvent.click(screen.getByRole('button', { name: '關閉放大表格' }));
    expect(screen.queryByRole('dialog', { name: '表格' })).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe('');

    fireEvent.click(expandButton);
    expect(screen.getByRole('dialog', { name: '表格' })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '表格' })).not.toBeInTheDocument();
  });

  it('removes the streaming reveal marker after live streaming ends', () => {
    const { container, rerender } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '串流動畫測試',
        }}
        isStreaming={true}
      />
    );

    expect(container.querySelector('[data-streaming-content="true"]')).toBeInTheDocument();

    rerender(
      <MessageItem
        message={{
          ...baseMessage,
          content: '串流動畫測試完成',
        }}
        isStreaming={false}
      />
    );

    expect(container.querySelector('[data-streaming-content="true"]')).not.toBeInTheDocument();
    expect(container.querySelector('.streamingDots')).not.toBeInTheDocument();
  });

  it('does not replay output animation when a completed assistant message is edited', () => {
    const { container, rerender } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '原本串流回答',
        }}
        isStreaming={true}
      />
    );

    expect(container.querySelector('[data-sd-animate]')).toBeInTheDocument();

    rerender(
      <MessageItem
        message={{
          ...baseMessage,
          content: '編輯後回答',
          updatedAt: new Date('2026-09-21T08:00:00.000Z'),
        }}
        isStreaming={false}
      />
    );

    expect(container.querySelector('[data-sd-animate]')).not.toBeInTheDocument();
    expect(container).toHaveTextContent('編輯後回答');
  });

  it('does not replay output animation for finished voice replies after editing', () => {
    const { container } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: '語音回答編輯後',
          voicePlayback: 'finished',
          updatedAt: new Date('2026-09-21T08:00:00.000Z'),
        }}
      />
    );

    expect(container.querySelector('[data-sd-animate]')).not.toBeInTheDocument();
    expect(container).toHaveTextContent('語音回答編輯後');
  });

  it('uses final structured blocks immediately when no live image slot event exists', () => {
    const streamedContent = '串流期間已顯示的回答';
    const { container, rerender } = render(
      <MessageItem
        message={{
          ...baseMessage,
          content: streamedContent,
        }}
        isStreaming={true}
      />
    );

    rerender(
      <MessageItem
        message={{
          ...baseMessage,
          content: streamedContent,
          answerBlocks: [
            { type: 'paragraph', text: '圖片前段' },
            {
              type: 'image_block',
              slotId: 'visual-after-stream',
              topic: 'Forest plot',
              purpose: 'diagram',
              imageUrl: 'https://example.com/forest.png',
              sourceUrl: 'https://example.com/article',
              sourceDomain: 'example.com',
              caption: 'Forest plot example',
              provider: 'wikimedia',
              explanatoryCaption: '完成後補上的圖片說明。',
              safetyStatus: 'pass',
              matchConfidence: 0.6,
            },
            { type: 'paragraph', text: '圖片後段' },
          ],
        }}
        isStreaming={false}
      />
    );

    expect(container).not.toHaveTextContent(streamedContent);
    const blocks = Array.from(container.querySelectorAll('[data-answer-block-index]'));
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toHaveTextContent('圖片前段');
    expect(blocks[1]).toHaveTextContent('完成後補上的圖片說明。');
    expect(blocks[2]).toHaveTextContent('圖片後段');
    expect(screen.getByText('完成後補上的圖片說明。')).toBeInTheDocument();
  });

  it('keeps live text nodes stable while resolving an image at its streamed slot', () => {
    const before = '圖片前段';
    const after = '\n\n圖片後段';
    const content = `${before}${after}`;
    const answerBlocks = [
      { type: 'paragraph' as const, text: before },
      {
        type: 'image_block' as const,
        slotId: 'img_1',
        topic: 'Forest plot',
        purpose: 'diagram',
        imageUrl: 'https://example.com/forest.png',
        sourceUrl: 'https://example.com/article',
        sourceDomain: 'example.com',
        caption: 'Forest plot example',
        safetyStatus: 'pass' as const,
        matchConfidence: 0.8,
      },
      { type: 'paragraph' as const, text: '圖片後段' },
    ];
    const liveMessage = {
      ...baseMessage,
      content,
      streamImageSlots: [{
        slotId: 'img_1',
        anchorAfterParagraph: 0,
        contentOffset: before.length,
      }],
    };
    const { container, rerender, unmount } = render(
      <MessageItem message={liveMessage} isStreaming={true} />
    );

    const initialParts = Array.from(container.querySelectorAll('[data-live-answer-part]'));
    expect(initialParts.map((part) => part.getAttribute('data-live-answer-part'))).toEqual([
      'live-text-start',
      'live-image-img_1',
      'live-text-after-img_1',
    ]);
    expect(screen.getByRole('status', { name: '圖片搜尋中' })).toBeInTheDocument();
    const stableBeforeNode = initialParts[0];

    rerender(
      <MessageItem
        message={{ ...liveMessage, answerBlocks }}
        isStreaming={false}
      />
    );

    const resolvedParts = Array.from(container.querySelectorAll('[data-live-answer-part]'));
    expect(resolvedParts[0]).toBe(stableBeforeNode);
    expect(resolvedParts.map((part) => part.getAttribute('data-live-answer-part'))).toEqual([
      'live-text-start',
      'live-image-img_1',
      'live-text-after-img_1',
    ]);
    expect(screen.getByAltText('Forest plot example')).toBeInTheDocument();

    unmount();
    const historical = render(
      <MessageItem
        message={{ ...baseMessage, content, answerBlocks }}
        isStreaming={false}
      />
    );
    const historicalBlocks = Array.from(
      historical.container.querySelectorAll('[data-answer-block-index]')
    );
    expect(historicalBlocks).toHaveLength(3);
    expect(historicalBlocks[0]).toHaveTextContent(before);
    expect(historicalBlocks[1].querySelector('img')).toHaveAttribute('alt', 'Forest plot example');
    expect(historicalBlocks[2]).toHaveTextContent('圖片後段');
  });

  it('uses complete structured blocks after streaming when live image slots are incomplete', () => {
    const answerBlocks = [
      { type: 'paragraph' as const, text: '第一段' },
      ...[1, 2, 3, 4].map((index) => ({
        type: 'image_block' as const,
        slotId: `img_${index}`,
        topic: `Figure ${index}`,
        purpose: 'diagram' as const,
        imageUrl: `https://example.com/figure-${index}.png`,
        sourceUrl: 'https://example.com/article',
        sourceDomain: 'example.com',
        caption: `Figure ${index} caption`,
        safetyStatus: 'pass' as const,
        matchConfidence: 0.8,
      })),
      { type: 'paragraph' as const, text: '最後一段' },
    ];
    const liveMessage = {
      ...baseMessage,
      content: '第一段\n\n最後一段',
      streamImageSlots: [
        { slotId: 'img_1', anchorAfterParagraph: 0, contentOffset: 3 },
        { slotId: 'img_2', anchorAfterParagraph: 0, contentOffset: 6 },
      ],
    };
    const { container, rerender } = render(
      <MessageItem message={liveMessage} isStreaming={true} />
    );

    expect(container.querySelectorAll('[data-live-answer-part]')).not.toHaveLength(0);

    rerender(
      <MessageItem
        message={{ ...liveMessage, answerBlocks }}
        isStreaming={false}
      />
    );

    expect(container.querySelectorAll('[data-live-answer-part]')).toHaveLength(0);
    expect(container.querySelectorAll('[data-answer-block-index]')).toHaveLength(6);
    expect(screen.getByAltText('Figure 1 caption')).toBeInTheDocument();
    expect(screen.getByAltText('Figure 2 caption')).toBeInTheDocument();
    expect(screen.getByAltText('Figure 3 caption')).toBeInTheDocument();
    expect(screen.getByAltText('Figure 4 caption')).toBeInTheDocument();
  });

  it('gates structured voice answers behind playback captions until speech finishes', async () => {
    const message = {
      ...baseMessage,
      content: 'Spoken sentence. Future sentence.',
      voicePlayback: 'playing' as const,
      voiceCaption: 'Spoken sentence.',
      answerBlocks: [{ type: 'paragraph' as const, text: 'Future sentence.' }],
    };
    const { rerender, container } = render(<MessageItem message={message} />);
    expect(container.querySelector('[data-role="assistant-bubble"]')).toHaveTextContent('Spoken sentence.');
    expect(container.querySelector('[data-role="assistant-bubble"]')).not.toHaveTextContent('Future sentence.');
    rerender(<MessageItem message={{ ...message, voicePlayback: 'finished', voiceCaption: undefined }} />);
    expect(await screen.findByText('Future sentence.')).toBeInTheDocument();
  });

});
