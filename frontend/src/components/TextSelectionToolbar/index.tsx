'use client';

import React, { useMemo } from 'react';
import { Copy, Quote, Sparkles } from 'lucide-react';
import { App } from 'antd';
import { useChatStore } from '@/store/chat';
import { sendMessage } from '@/services/chat';
import { useTextSelection } from '@/hooks/useTextSelection';
import { useStyles } from './styles';

/**
 * TextSelectionToolbar Component
 * Floating toolbar for text selection actions
 */
export function TextSelectionToolbar() {
  const { styles, cx } = useStyles();
  const { message } = App.useApp();
  const { text, rect, clearSelection } = useTextSelection();
  const setQuotedText = useChatStore((state) => state.setQuotedText);

  const position = useMemo(() => {
    if (!rect) return null;
    
    // Position above the selection
    const top = rect.top - 52;
    // With labels, the toolbar is wider. Centering logic:
    // rect.left + rect.width / 2 is the center of selection.
    // We adjust based on estimated toolbar width (now around 280px)
    const left = rect.left + rect.width / 2 - 140; 
    
    return {
      top: Math.max(8, top),
      left: Math.max(8, left),
    };
  }, [rect]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      message.success('已複製到剪貼簿');
      clearSelection();
    } catch {
      message.error('複製失敗');
    }
  };

  const handleQuote = () => {
    setQuotedText(text);
    clearSelection();
    // Focus chat input (optional, could be handled via global state if needed)
  };

  const handleExplain = async () => {
    const prompt = `請幫我解釋這段文字：\n\n> ${text}`;
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
      <button className={styles.button} onClick={handleCopy} aria-label="複製">
        <Copy size={14} />
        <span className={styles.label}>複製</span>
      </button>
      
      <div className={styles.divider} />
      
      <button className={styles.button} onClick={handleQuote} aria-label="問小紅">
        <Quote size={14} />
        <span className={styles.label}>問小紅(引用)</span>
      </button>

      <div className={styles.divider} />

      <button className={styles.button} onClick={handleExplain} aria-label="幫我解釋">
        <Sparkles size={14} />
        <span className={styles.label}>幫我解釋</span>
      </button>
    </div>
  );
}

export default TextSelectionToolbar;
