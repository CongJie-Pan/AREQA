import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const { prefetch } = vi.hoisted(() => ({ prefetch: vi.fn() }));
vi.mock('@/utils/attachmentPreview', () => ({
  isPdfFile: (file: File) => file.type === 'application/pdf',
  prefetchAttachmentPreview: prefetch,
}));

import { ComposerAttachmentTile } from '../../../../frontend/src/components/ChatInput/ComposerAttachmentTile';

const props = {
  imageAlt: '圖片附件預覽',
  lineCountLabel: (count: number) => `${count} 行`,
  lowResLabel: '解析度低',
};

describe('ComposerAttachmentTile', () => {
  it('shows a text file as name, line count and type badge', async () => {
    const file = new File(['a\nb\nc'], 'logs.txt', { type: 'text/plain' });
    render(<ComposerAttachmentTile {...props} file={file} objectUrl={null} removeLabel="刪除 logs.txt" onRemove={vi.fn()} />);

    expect(screen.getByText('logs.txt')).toBeInTheDocument();
    expect(screen.getByText('TXT')).toBeInTheDocument();
    expect(await screen.findByText('3 行')).toBeInTheDocument();
  });

  it('shows a PDF first page once its thumbnail is ready, with a PDF badge', async () => {
    prefetch.mockResolvedValueOnce({ dataUrl: 'data:image/jpeg;base64,/9j/', width: 400, height: 300 });
    const file = new File(['%PDF'], 'areqa-chat.pdf', { type: 'application/pdf' });
    const { container } = render(<ComposerAttachmentTile {...props} file={file} objectUrl={null} removeLabel="刪除" onRemove={vi.fn()} />);

    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'data:image/jpeg;base64,/9j/'));
    expect(screen.getByText('PDF')).toBeInTheDocument();
  });

  it('falls back to the file name for a PDF without a thumbnail', async () => {
    prefetch.mockResolvedValueOnce(undefined);
    const file = new File(['%PDF'], 'encrypted.pdf', { type: 'application/pdf' });
    render(<ComposerAttachmentTile {...props} file={file} objectUrl={null} removeLabel="刪除" onRemove={vi.fn()} />);

    expect(screen.getByText('encrypted.pdf')).toBeInTheDocument();
    expect(screen.getByText('PDF')).toBeInTheDocument();
  });

  it('renders images and removes on request', () => {
    const onRemove = vi.fn();
    const file = new File(['png'], 'photo.png', { type: 'image/png' });
    render(<ComposerAttachmentTile {...props} file={file} objectUrl="blob:photo" removeLabel="刪除 photo.png" onRemove={onRemove} />);

    expect(screen.getByAltText('圖片附件預覽')).toHaveAttribute('src', 'blob:photo');
    fireEvent.click(screen.getByRole('button', { name: '刪除 photo.png' }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
