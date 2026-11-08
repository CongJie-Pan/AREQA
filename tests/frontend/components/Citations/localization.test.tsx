import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { Citations } from '../../../../frontend/src/components/Citations';
import {
  UserPreferencesProvider,
  useUserPreferences,
  type InterfaceLanguage,
} from '../../../../frontend/src/contexts/UserPreferencesContext';

function LanguageControls() {
  const { setLanguage } = useUserPreferences();
  return <>{(['en', 'zh-TW', 'zh-CN'] as InterfaceLanguage[]).map(language => (
    <button key={language} onClick={() => setLanguage(language)}>{language}</button>
  ))}</>;
}

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe('Citations interface language', () => {
  it.each([
    ['en', 'Sources', 'Source details', 'Source', 'Identifier: local-chunk'],
    ['zh-TW', '文獻來源', '文獻原文詳情', '文獻來源', '識別碼: local-chunk'],
    ['zh-CN', '文献来源', '文献原文详情', '文献来源', '标识符: local-chunk'],
  ])('translates the header, untitled source and details in %s', (language, heading, details, fallback, identifier) => {
    render(<UserPreferencesProvider>
      <LanguageControls />
      <Citations messageId="local-citation" defaultExpanded sources={[
        { title: '', snippet: 'Original source text', chunk_id: 'local-chunk' },
      ]} />
    </UserPreferencesProvider>);
    fireEvent.click(screen.getByRole('button', { name: language, exact: true }));
    expect(screen.getAllByText(heading).length).toBeGreaterThan(0);
    const cardTitle = screen.getAllByText(fallback).find(element => element.tagName === 'P');
    expect(cardTitle).toBeDefined();
    fireEvent.click(cardTitle!);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(details)).toBeInTheDocument();
    expect(within(dialog).getByText(identifier)).toBeInTheDocument();
    expect(within(dialog).getByText('Original source text')).toBeInTheDocument();
  });

  it('updates an already open detail modal when the language changes', () => {
    render(<UserPreferencesProvider>
      <LanguageControls />
      <Citations messageId="web-citation" defaultExpanded sources={[
        { title: 'Sample paper', snippet: 'Original source text', chunk_id: 'https://example.com/paper' },
      ]} />
    </UserPreferencesProvider>);
    fireEvent.click(screen.getByText('Sample paper'));
    expect(within(screen.getByRole('dialog')).getByText('Source details')).toBeInTheDocument();
    expect(within(screen.getByRole('dialog')).getByRole('link', { name: 'Open source in a new tab' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'zh-TW', exact: true }));
    expect(within(screen.getByRole('dialog')).getByText('文獻原文詳情')).toBeInTheDocument();
    expect(within(screen.getByRole('dialog')).getByRole('link', { name: '在新分頁開啟原文' })).toBeInTheDocument();
  });
});
