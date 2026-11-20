import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { SharedOwnerBar } from '../../../../frontend/src/components/SharedConversation';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

describe('SharedOwnerBar', () => {
  beforeEach(() => {
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('tells the owner it is their read-only copy', () => {
    render(<UserPreferencesProvider><SharedOwnerBar onOpenOriginal={() => {}} /></UserPreferencesProvider>);
    expect(screen.getByRole('note')).toHaveTextContent('這是你分享的對話的唯讀副本。');
    expect(screen.getByRole('button', { name: '開啟原始對話' })).toBeInTheDocument();
  });

  it('shows other viewers a read-only notice without owner actions', () => {
    render(<UserPreferencesProvider><SharedOwnerBar notice="這是唯讀的分享對話，無法在這裡提問。" /></UserPreferencesProvider>);
    expect(screen.getByRole('note')).toHaveTextContent('這是唯讀的分享對話，無法在這裡提問。');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
