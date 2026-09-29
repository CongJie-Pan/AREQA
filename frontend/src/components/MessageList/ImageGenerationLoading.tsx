'use client';

import React, { useEffect, useState } from 'react';
import { ImagePlus, LoaderCircle } from 'lucide-react';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { useStyles } from './styles';

/** Render image preparation/generation feedback without inventing progress.
 *
 * Args:
 *   caption: Current preparation or generation phase.
 *   frameStyle: Reserved image dimensions, defaulting to the standard preview.
 *   canStop: Whether this is cancellable generation rather than URL renewal.
 * Side Effects:
 *   Shows a reassurance after twenty seconds; the timer is cleared on unmount.
 */
export function ImageGenerationLoading({ caption, frameStyle = { aspectRatio: '16 / 9' }, canStop = true }: {
  caption: string;
  frameStyle?: React.CSSProperties;
  canStop?: boolean;
}) {
  const { styles } = useStyles();
  const { language } = useUserPreferences();
  const [isTakingLonger, setIsTakingLonger] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsTakingLonger(true), 20_000);
    return () => window.clearTimeout(timer);
  }, []);

  const label = language === 'en' ? 'Creating image' : language === 'zh-CN' ? '图片生成中' : '圖片產生中';
  const hint = isTakingLonger
    ? language === 'en' ? 'Still creating your image. Please wait…' : language === 'zh-CN' ? '仍在生成中，请稍候…' : '仍在生成中，請稍候…'
    : language === 'en' ? 'You can stop generation at any time.' : language === 'zh-CN' ? '你可以随时停止生成。' : '你可以隨時停止生成。';

  return (
    <figure className={styles.answerImageCard} aria-label={label}>
      <div className={styles.generatedImagePendingFrame} style={frameStyle} role="status" aria-label={label} aria-live="polite">
        <div className={styles.generatedImageShimmer} aria-hidden="true" data-testid="answer-image-skeleton" />
        <div className={styles.generatedImagePendingContent}>
          <ImagePlus size={30} aria-hidden="true" />
          <span className={styles.generatedImagePendingTitle}>
            <LoaderCircle size={16} className={styles.generatedImagePendingSpinner} aria-hidden="true" />
            {caption}
          </span>
          {canStop && <span className={styles.generatedImagePendingHint}>{hint}</span>}
        </div>
      </div>
    </figure>
  );
}
