import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AttachmentCard } from '../../../../frontend/src/components/MessageList/AttachmentCard';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import { clearSessionAttachments, rememberSessionAttachments } from '../../../../frontend/src/utils/attachmentSession';
import type { AttachmentMetadata } from '../../../../frontend/src/database/schema';

vi.mock('@/utils/attachmentPreview', () => ({
  renderPdfFirstPage: vi.fn(async () => ({ dataUrl: 'data:image/jpeg;base64,TEFSR0U=', width: 960, height: 720 })),
}));

const thumb = { dataUrl: 'data:image/jpeg;base64,/9j/4AAQ', width: 400, height: 225 };
const image: AttachmentMetadata = { name: 'chart.png', mediaType: 'image/png', sizeBytes: 2048, preview: thumb };
const pdf: AttachmentMetadata = { name: 'Ch08_Motivation.pdf', mediaType: 'application/pdf', sizeBytes: 4096, preview: thumb };

const renderCard = (props: React.ComponentProps<typeof AttachmentCard>) => render(
  <UserPreferencesProvider><AttachmentCard {...props} /></UserPreferencesProvider>,
);

describe('AttachmentCard previews', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    vi.stubGlobal('URL', Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:original'),
      revokeObjectURL: vi.fn(),
    }));
  });

  afterEach(() => {
    clearSessionAttachments();
  });

  it('keeps the plain file card when no thumbnail was stored', () => {
    renderCard({ attachment: { name: 'old.pdf', mediaType: 'application/pdf', sizeBytes: 2048 } });
    expect(screen.queryByRole('button', { name: /預覽/ })).not.toBeInTheDocument();
    expect(screen.getByText('old.pdf')).toBeInTheDocument();
  });

  it('shows an image thumbnail at its proportions and opens the answer-style viewer', () => {
    renderCard({ attachment: image, messageId: 'm1', index: 0 });
    const thumbImage = screen.getByRole('button', { name: '預覽 chart.png' }).querySelector('img');
    expect(thumbImage).toHaveAttribute('width', '400');
    expect(thumbImage).toHaveAttribute('height', '225');

    fireEvent.click(screen.getByRole('button', { name: '預覽 chart.png' }));
    const viewer = screen.getByRole('dialog', { name: 'chart.png' });
    expect(viewer.querySelector('img')).toHaveAttribute('src', thumb.dataUrl);
    expect(screen.queryByRole('link', { name: '下載' })).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the full original and a download while the upload session is open', () => {
    rememberSessionAttachments('m1', [new File(['png'], 'chart.png', { type: 'image/png' })]);
    renderCard({ attachment: image, messageId: 'm1', index: 0 });
    fireEvent.click(screen.getByRole('button', { name: '預覽 chart.png' }));

    expect(screen.getByRole('dialog').querySelector('img')).toHaveAttribute('src', 'blob:original');
    expect(screen.getByRole('link', { name: '下載' })).toHaveAttribute('download', 'chart.png');
  });

  it('renders a PDF tile and a dialog with name, first page and download', async () => {
    rememberSessionAttachments('m2', [new File(['%PDF'], 'Ch08_Motivation.pdf', { type: 'application/pdf' })]);
    renderCard({ attachment: pdf, messageId: 'm2', index: 0 });
    expect(screen.getByText('PDF')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '預覽 Ch08_Motivation.pdf' }));
    const dialog = screen.getByRole('dialog', { name: 'Ch08_Motivation.pdf' });
    expect(screen.getByRole('heading', { name: 'Ch08_Motivation.pdf' })).toBeInTheDocument();
    await waitFor(() => expect(dialog.querySelector('img')).toHaveAttribute('src', 'data:image/jpeg;base64,TEFSR0U='));
    expect(screen.getByRole('link', { name: '下載' })).toHaveAttribute('href', 'blob:original');

    fireEvent.click(screen.getByRole('button', { name: '關閉預覽' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('explains that only the thumbnail remains after a reload', () => {
    renderCard({ attachment: pdf, messageId: 'reloaded', index: 0 });
    fireEvent.click(screen.getByRole('button', { name: '預覽 Ch08_Motivation.pdf' }));

    expect(screen.getByRole('dialog').querySelector('img')).toHaveAttribute('src', thumb.dataUrl);
    expect(screen.queryByRole('link', { name: '下載' })).not.toBeInTheDocument();
    expect(screen.getByText(/重新整理後只保留預覽縮圖/)).toBeInTheDocument();
  });
});
