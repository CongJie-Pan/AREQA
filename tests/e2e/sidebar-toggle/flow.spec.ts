import { resolve } from 'node:path';
import { expect, test } from '../../../frontend/node_modules/@playwright/test/index.mjs';

for (const width of [390, 768, 769, 1100]) {
  test(`actual pointer clicks reach the sidebar toggle at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 860 });
    await page.addInitScript(() => localStorage.setItem('areqa:interface-theme', 'light'));
    await page.goto('/');
    const toggle = page.locator('.areqa-chat-sidebar-toggle');
    await expect(toggle).toBeVisible();
    const initial = width > 768;
    await expect(toggle).toHaveAttribute('aria-expanded', String(initial));
    for (let count = 0; count < 4; count++) {
      // Visibility alone does not prove that a hit at the button reaches it.
      await expect.poll(() => toggle.evaluate(element => {
        const box = element.getBoundingClientRect();
        return element.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
      })).toBe(true);
      const open = await toggle.getAttribute('aria-expanded') === 'true';
      const buttonBox = await toggle.boundingBox();
      expect(buttonBox).not.toBeNull();
      expect(buttonBox!.x).toBeCloseTo(8, 0);
      expect(buttonBox!.y).toBeCloseTo(4, 0);
      if (open) {
        const brandBox = await page.locator('.areqa-conversation-logo-wrapper').boundingBox();
        expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(brandBox!.x);
      }
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', String(count % 2 === 0 ? !initial : initial));
    }
  });
}

test('dragging to the visible minimum collapses before pointer release', async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 860 });
  await page.goto('/');
  const handle = page.locator('.areqa-chat-sidebar-resize');
  const toggle = page.locator('.areqa-chat-sidebar-toggle');
  await expect(handle).toBeVisible();
  const box = (await handle.boundingBox())!;
  const startX = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(startX, y);
  await page.mouse.down();
  await page.mouse.move(startX - 59, y);
  await expect(handle).toHaveAttribute('aria-valuenow', '221');
  await page.mouse.move(startX - 60, y);
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await page.mouse.up();
  await toggle.click();
  await expect(handle).toHaveAttribute('aria-valuenow', '280');
});

test('content compositing cannot move or block the navigation control', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 860 });
  await page.goto('/');
  const toggle = page.locator('.areqa-chat-sidebar-toggle');
  await expect(toggle).toBeVisible();
  // Content panes may acquire their own containing/stacking context. Navigation
  // must remain outside that clipping boundary and above the mobile drawer.
  await page.locator('.areqa-chat-main').evaluate(element => { element.style.transform = 'translateZ(0)'; });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect.poll(() => toggle.evaluate(element => {
    const box = element.getBoundingClientRect();
    return element.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
  })).toBe(true);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
});

test.describe('touch navigation', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 860 } });
  test('repeated taps open and close the actual drawer', async ({ page }) => {
    await page.goto('/');
    const toggle = page.locator('.areqa-chat-sidebar-toggle');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    for (let count = 0; count < 4; count++) {
      await toggle.tap();
      await expect(toggle).toHaveAttribute('aria-expanded', String(count % 2 === 0));
    }
  });
});

for (const theme of ['light', 'dark']) {
  test(`sidebar control provides visible feedback in ${theme} mode`, async ({ page }) => {
    await page.addInitScript(theme => localStorage.setItem('areqa:interface-theme', theme), theme);
    await page.setViewportSize({ width: 1100, height: 860 });
    await page.goto('/');
    const toggle = page.locator('.areqa-chat-sidebar-toggle');
    await expect(toggle).toBeVisible();
    await page.mouse.move(600, 400);
    const color = await toggle.evaluate(element => getComputedStyle(element).color);
    await expect(toggle).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(toggle).toHaveCSS('box-shadow', 'none');
    await toggle.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await expect.poll(() => toggle.evaluate(element => getComputedStyle(element).color)).not.toBe(color);
    await expect(toggle).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await page.mouse.move(600, 400);
    await toggle.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveCSS('outline-style', 'solid');
    await page.screenshot({ path: `/tmp/areqa-sidebar-button-${theme}.png` });
    await toggle.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
}

test('reduced motion keeps hover and press stationary', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1100, height: 860 });
  await page.goto('/');
  const toggle = page.locator('.areqa-chat-sidebar-toggle');
  await toggle.hover();
  await expect(toggle).toHaveCSS('transform', 'none');
  await expect(toggle).toHaveCSS('transition-duration', '0s');
  await page.mouse.down();
  await expect(toggle).toHaveCSS('transform', 'none');
  await page.mouse.up();
});


test.describe('sidebar first paint without client scripts', () => {
  test.use({ javaScriptEnabled: false });
  for (const theme of ['light', 'dark']) {
    test(`global CSS renders the complete button in ${theme} mode`, async ({ page }) => {
      const cssPath = resolve(__dirname, '../../../frontend/src/app/globals.css');
      await page.route('**/sidebar-first-paint', route => route.fulfill({
        contentType: 'text/html',
        body: `<html data-interface-theme="${theme}"><head><meta charset="utf-8"><link rel="stylesheet" href="/@fs${cssPath}?direct"></head><body>
          <div class="areqa-chat-sidebar" data-mobile-open="false">
            <div class="areqa-conversation-list">
              <div class="areqa-conversation-logo-row areqa-conversation-logo-row-external-toggle">AREQA</div>
              <div class="areqa-conversation-actions">
                <button class="areqa-conversation-new-button">New chat</button>
                <button class="areqa-conversation-search-button">Search chats</button>
              </div>
              <div class="areqa-conversation-scroll-list">
                <div class="areqa-conversation-item">Sample conversation</div>
              </div>
            </div>
          </div>
          <button class="areqa-chat-sidebar-toggle" aria-label="Open sidebar">☰</button>
        </body></html>`,
      }));
      await page.goto('/sidebar-first-paint');
      await expect(page.locator('.areqa-conversation-logo-row')).toHaveCSS('padding-left', '46px');
      await expect(page.locator('.areqa-conversation-actions')).toHaveCSS('flex-direction', 'column');
      await expect(page.getByRole('button', { name: 'Search chats' })).toHaveCSS('min-height', '34px');
      await expect(page.locator('.areqa-conversation-item')).toHaveCSS('min-height', '34px');
      const toggle = page.getByRole('button', { name: 'Open sidebar' });
      await expect(toggle).toHaveCSS('border-top-width', '0px');
      await expect(toggle).toHaveCSS('box-shadow', 'none');
      await expect(toggle).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    });
  }
});
