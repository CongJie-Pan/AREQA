import { expect, test } from '../../../frontend/node_modules/@playwright/test/index.mjs';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, { cascadeFades: [] });
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (...args) {
      const animation = animate.apply(this, args);
      if (this.hasAttribute('data-sd-animate')) {
        const state = window as unknown as { cascadeFades: unknown[]; freezeFirstFade?: boolean };
        // Pause mid-fade so parser continuity is independent of CI execution speed.
        if (state.freezeFirstFade && state.cascadeFades.length === 0) { animation.pause(); animation.currentTime = 60; }
        state.cascadeFades.push({ text: this.textContent, node: this, animation });
      }
      return animation;
    };
  });
  await page.goto('/');
  await page.waitForFunction(() => typeof window.cascadeReplay === 'function');
});

test('keeps packet and paragraph playback ordered, preserves running fades, and drains without remounting', async ({ page }) => {
  const first = `開頭${'甲'.repeat(80)}`;
  const full = `${first}\n\n第二段${'乙'.repeat(40)}`;
  await page.evaluate(content => { Object.assign(window, { freezeFirstFade: true }); window.cascadeReplay(content, true); }, first);
  const bubble = page.locator('[data-role="assistant-bubble"]');
  await expect.poll(() => bubble.textContent()).toContain('開頭');
  const initialLength = await bubble.textContent();
  expect(initialLength).not.toContain('甲'.repeat(80));
  await page.evaluate(() => {
    const entries = (window as unknown as { cascadeFades: { node: Element; animation: Animation }[] }).cascadeFades;
    Object.assign(window, { firstFade: entries[0], firstSpan: document.querySelector('[data-sd-animate]') });
  });
  await page.evaluate(content => window.cascadeReplay(content, true), full);
  expect(await bubble.textContent()).not.toContain('第二段');
  await expect.poll(() => page.evaluate(() => {
    const first = (window as unknown as { firstFade: { node: Element; animation: Animation } }).firstFade;
    return first.node.getAnimations().includes(first.animation) && first.animation.playState === 'paused' && first.animation.currentTime === 60;
  })).toBe(true);
  await page.evaluate(() => (window as unknown as { firstFade: { animation: Animation } }).firstFade.animation.play());
  await page.evaluate(content => window.cascadeReplay(content, false), full);
  await expect(bubble).toContainText('第二段');
  await expect(bubble).toContainText('乙'.repeat(40));
  expect(await page.evaluate(() => document.querySelector('[data-sd-animate]') === (window as unknown as { firstSpan: Element }).firstSpan)).toBe(true);
  expect(await page.evaluate(() => (window as unknown as { cascadeFades: { text: string }[] }).cascadeFades.filter(fade => fade.text === '開').length)).toBe(1);
});

test('paces image anchors and keeps Markdown, citations, math and tables functional', async ({ page }) => {
  const before = '前'.repeat(100);
  const full = `${before}\n\n**粗體** [1](#cite-1)\n\n$x^2$\n\n| A | B |\n|---|---|\n| 1 | 2 |`;
  await page.evaluate(({ full, offset }) => window.cascadeReplay(full, true, [
    { slotId: 'future-image', anchorAfterParagraph: 0, contentOffset: offset },
  ]), { full, offset: before.length });
  const image = page.locator('[data-live-answer-part="live-image-future-image"]');
  await expect(image).toHaveCount(0);
  await expect(page.locator('[data-role="assistant-bubble"]')).toContainText('前');
  await expect(image).toHaveCount(0);
  await expect(image).toHaveCount(1);
  await expect(page.locator('strong').filter({ hasText: '粗體' })).toBeVisible();
  await expect(page.locator('a[href="#cite-1"]')).toBeVisible();
  await expect(page.locator('.katex').first()).toBeVisible();
  await expect(page.locator('table')).toBeVisible();
});

test('honors reduced motion and renders completed history immediately', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  await page.waitForFunction(() => typeof window.cascadeReplay === 'function');
  const full = '完整回答'.repeat(100);
  await page.evaluate(content => window.cascadeReplay(content, true), full);
  await expect(page.locator('[data-role="assistant-bubble"]')).toContainText(full);
  expect(await page.evaluate(() => (window as unknown as { cascadeFades: unknown[] }).cascadeFades.length)).toBe(0);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.reload();
  await page.waitForFunction(() => typeof window.cascadeReplay === 'function');
  await page.evaluate(content => window.cascadeReplay(content, false), full);
  await expect(page.locator('[data-role="assistant-bubble"]')).toContainText(full);
  await expect(page.locator('[data-sd-animate]')).toHaveCount(0);
});
