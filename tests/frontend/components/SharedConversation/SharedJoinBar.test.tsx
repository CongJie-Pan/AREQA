import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { authenticatedFetch } = vi.hoisted(() => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch }));

import { SharedJoinBar } from '../../../../frontend/src/components/SharedConversation';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

const TOKEN = 'L-GIo3nG6ceEijhdinSsm3A3';

describe('SharedJoinBar', () => {
  const assign = vi.fn();

  beforeEach(() => {
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    vi.stubGlobal('location', { ...window.location, assign });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    authenticatedFetch.mockReset();
    assign.mockReset();
  });

  it('joins with the share token and opens the collaborative page', async () => {
    authenticatedFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ conversationId: 'c-1' }) });
    render(<UserPreferencesProvider><SharedJoinBar token={TOKEN} /></UserPreferencesProvider>);

    fireEvent.click(screen.getByRole('button', { name: '加入共同對話' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/collab/c-1'));
    expect(JSON.parse(authenticatedFetch.mock.calls[0][1].body)).toEqual({ token: TOKEN });
  });

  it('explains when the link no longer allows joining', async () => {
    authenticatedFetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });
    render(<UserPreferencesProvider><SharedJoinBar token={TOKEN} /></UserPreferencesProvider>);

    fireEvent.click(screen.getByRole('button', { name: '加入共同對話' }));
    expect(await screen.findByText('無法加入這段對話，連結可能已改為僅檢視。')).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
