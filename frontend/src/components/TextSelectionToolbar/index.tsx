'use client';

import React, { useMemo } from 'react';
import { Copy, Quote, Sparkles } from 'lucide-react';
import { App } from 'antd';
import { useChatStore } from '@/store/chat';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { sendMessage } from '@/services/chat';
import { useTextSelection } from '@/hooks/useTextSelection';
import { useStyles } from './styles';

function formatSelectedTextAsQuote(text: string): string {
  return text
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');
}

/**
 * TextSelectionToolbar Component
 * Floating toolbar for text selection actions
 */
export function TextSelectionToolbar() {
  const { styles, cx } = useStyles();
  const { message } = App.useApp();
  const { t } = useUserPreferences();
  const { text, rect, clearSelection } = useTextSelection();
  const setQuotedText = useChatStore((state) => state.setQuotedText);

  const position = useMemo(() => {
    if (!rect) return null;
    
    const top = rect.top - 52;
    const left = rect.left + rect.width / 2;
    
    return {
      top: Math.max(8, top),
      left: Math.max(8, left),
    };
  }, [rect]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(t('copyMessageSuccess'));
      clearSelection();
    } catch {
      message.error(t('copyMessageFailed'));
    }
  };

  const handleQuote = () => {
    setQuotedText(text);
    clearSelection();
    // Focus chat input (optional, could be handled via global state if needed)
  };

  const handleExplain = async () => {
    const prompt = t('textSelectionExplainPrompt', {
      text: formatSelectedTextAsQuote(text),
    });
    clearSelection();
    await sendMessage(prompt);
  };

  if (!text || !position) return null;

  return (
    <div
      className={cx(styles.toolbar, 'selection-toolbar')}
      style={{
        top: position.top,
        left: position.left,
      }}
      onMouseDown={(e) => e.preventDefault()} // Prevent losing selection
    >
      <button className={styles.button} onClick={handleCopy} aria-label={t('textSelectionCopy')}>
        <Copy size={14} />
        <span className={styles.label}>{t('textSelectionCopy')}</span>
      </button>
      
      <div className={styles.divider} />
      
      <button className={styles.button} onClick={handleQuote} aria-label={t('textSelectionAskQuote')}>
        <Quote size={14} />
        <span className={styles.label}>{t('textSelectionAskQuote')}</span>
      </button>

      <div className={styles.divider} />

      <button className={styles.button} onClick={handleExplain} aria-label={t('textSelectionExplain')}>
        <Sparkles size={14} />
        <span className={styles.label}>{t('textSelectionExplain')}</span>
      </button>
    </div>
  );
}

export default TextSelectionToolbar;
