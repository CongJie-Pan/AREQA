import { useLayoutEffect, useRef, type RefObject } from 'react';

const FADE_MS = 180;

/**
 * Fade newly inserted text without restarting animations on existing spans.
 *
 * Args:
 *   root: Container whose Streamdown spans have zero-duration CSS animation.
 *   active: Whether new received/displayed text may start a fade.
 * Side effects:
 *   Observes committed DOM changes, including Streamdown's deferred block
 *   updates. Web Animations remain independent of reparsed inline styles.
 *   Reparented old Markdown text is excluded by a prefix/suffix comparison.
 *   Unsupported browsers fall back to the same paced text without fading.
 */
export function useStreamingTailFade(root: RefObject<HTMLDivElement | null>, active: boolean) {
  const running = useRef(new Set<Animation>());

  useLayoutEffect(() => {
    const element = root.current;
    if (!element || !active) return;
    const spans = () => Array.from(element.querySelectorAll<HTMLElement>('[data-sd-animate]'));
    const seen = new WeakSet<HTMLElement>();
    let previous = spans().map(span => { seen.add(span); return span.textContent ?? ''; }).join('');
    const observer = new MutationObserver(() => {
      const nodes = spans();
      const text = nodes.map(span => span.textContent ?? '').join('');
      let prefix = 0;
      while (prefix < previous.length && prefix < text.length && previous[prefix] === text[prefix]) prefix++;
      let suffix = 0;
      while (suffix < previous.length - prefix && suffix < text.length - prefix
        && previous[previous.length - suffix - 1] === text[text.length - suffix - 1]) suffix++;
      let offset = 0;
      for (const span of nodes) {
        const end = offset + (span.textContent?.length ?? 0);
        if (!seen.has(span) && end > prefix && offset < text.length - suffix && typeof span.animate === 'function') {
          const animation = span.animate([{ opacity: 0 }, { opacity: 1 }], { duration: FADE_MS, easing: 'ease-out' });
          running.current.add(animation);
          void animation.finished.then(
            () => running.current.delete(animation),
            () => running.current.delete(animation),
          );
        }
        seen.add(span);
        offset = end;
      }
      previous = text;
    });
    observer.observe(element, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [active, root]);

  useLayoutEffect(() => {
    const animations = running.current;
    return () => { for (const animation of animations) animation.cancel(); animations.clear(); };
  }, []);
}
