import React from 'react';
import { renderToString } from 'react-dom/server';
import { hydrateRoot, type Root } from 'react-dom/client';
import { act, cleanup, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UserPreferencesProvider, useUserPreferences } from '@/contexts/UserPreferencesContext';

function PreferenceSnapshot() {
  const { language, resolvedTheme } = useUserPreferences();
  return <span>{language}:{resolvedTheme}</span>;
}

describe('persisted preference hydration', () => {
  let root: Root | undefined;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(async () => {
    await act(async () => root?.unmount());
    root = undefined;
    cleanup();
    document.body.innerHTML = '';
  });

  it('restores legacy browser preferences without replacing the server tree', async () => {
    const tree = <UserPreferencesProvider><PreferenceSnapshot /></UserPreferencesProvider>;
    const container = document.createElement('div');
    container.innerHTML = renderToString(tree);
    document.body.append(container);
    localStorage.setItem('areqa:interface-language', 'zh-TW');
    localStorage.setItem('areqa:interface-theme', 'light');
    const onRecoverableError = vi.fn();

    await act(async () => {
      root = hydrateRoot(container, tree, { onRecoverableError });
    });

    await waitFor(() => expect(container.textContent).toBe('zh-TW:light'));
    expect(onRecoverableError).not.toHaveBeenCalled();
  });
});
