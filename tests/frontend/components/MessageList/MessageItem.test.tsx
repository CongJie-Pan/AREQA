import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';

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
      answerImageLightboxBody: 'answerImageLightboxBody',
      answerImageLightboxImage: 'answerImageLightboxImage',
      answerImageLightboxMeta: 'answerImageLightboxMeta',
      answerImageLightboxSource: 'answerImageLightboxSource',
      content: 'content',
      streamingCursor: 'streamingCursor'
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

// Mock markdown component
vi.mock('react-markdown', () => ({
  default: ({ children }: any) => <div>{children}</div>
}));

describe('MessageItem Integration with RAGStatusPanel', () => {
  const baseMessage = {
    id: 'msg-1',
    role: 'assistant' as const,
    content: '這是測試訊息',
    createdAt: Date.now(),
  };

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
    expect(screen.getByLabelText('訊息附件').closest('.userBubble')).not.toBeInTheDocument();
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

    expect(screen.getByLabelText('訊息附件').closest('.userBubble')).not.toBeInTheDocument();
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
    expect(screen.queryByLabelText('附件檔名列表')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('附件 first.pdf')).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const attachmentList = screen.getByLabelText('附件檔名列表');
    expect(attachmentList).toBeInTheDocument();
    expect(attachmentList.closest('.messageAttachmentList')).toBeNull();
    expect(screen.getByText('first.pdf')).toBeInTheDocument();
    expect(screen.getByText('second.pdf')).toBeInTheDocument();
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

    expect(screen.getByText('View original source')).toHaveAttribute('href', 'https://example.com/article');
    expect(screen.getByText('Attribution:')).toBeInTheDocument();
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

    expect(screen.getByText('串流動畫測試')).toBeInTheDocument();
    expect(container.querySelector('[data-streaming-content="true"]')).toBeInTheDocument();
    expect(container.querySelector('[data-sd-animate]')).not.toBeInTheDocument();
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
    expect(dialog.parentElement).toBe(document.body);
    expect(document.body.style.overflow).toBe('hidden');
    expect(screen.getByRole('heading', { name: '表格' })).toBeInTheDocument();

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
    expect(container.querySelector('[data-sd-animate]')).not.toBeInTheDocument();

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
    expect(container.querySelector('[data-sd-animate]')).not.toBeInTheDocument();
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
});
