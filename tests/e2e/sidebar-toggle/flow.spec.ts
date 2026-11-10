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
      const sidebarBox = await page.locator('.areqa-chat-sidebar').boundingBox();
      const buttonBox = await toggle.boundingBox();
      expect(sidebarBox).not.toBeNull();
      expect(buttonBox).not.toBeNull();
      const expectedLeft = open ? sidebarBox!.width - 52 : 16;
      expect(buttonBox!.x).toBeCloseTo(expectedLeft, 0);
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', String(count % 2 === 0 ? !initial : initial));
    }
  });
}

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
    const background = await toggle.evaluate(element => getComputedStyle(element).backgroundColor);
    const shadow = await toggle.evaluate(element => getComputedStyle(element).boxShadow);
    await expect(toggle).toHaveCSS('border-radius', '10px');
    await toggle.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await expect.poll(() => toggle.evaluate(element => getComputedStyle(element).boxShadow)).not.toBe(shadow);
    await expect.poll(() => toggle.evaluate(element => new DOMMatrix(getComputedStyle(element).transform).m42)).toBe(-1);
    await expect.poll(() => toggle.evaluate(element => getComputedStyle(element).backgroundColor)).not.toBe(background);
    await page.mouse.down();
    await expect.poll(() => toggle.evaluate(element => new DOMMatrix(getComputedStyle(element).transform).a)).toBeCloseTo(0.95, 2);
    await page.mouse.move(600, 400);
    await page.mouse.up();
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
