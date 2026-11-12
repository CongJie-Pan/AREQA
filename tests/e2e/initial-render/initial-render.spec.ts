import { test, expect, type Page } from '../../../frontend/node_modules/@playwright/test/index.mjs';

async function geometry(page: Page) {
  return page.locator('.areqa-chat-input-shell').evaluate(shell => {
    const rect = shell.getBoundingClientRect();
    const style = getComputedStyle(shell);
    const textarea = shell.querySelector('textarea')!;
    const toggle = document.querySelector('.areqa-chat-sidebar-toggle')!;
    return {
      x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      radius: style.borderRadius, padding: style.padding, background: style.backgroundColor,
      toggleX: toggle.getBoundingClientRect().x,
      textareaFont: getComputedStyle(textarea).fontSize,
      textareaHeight: textarea.clientHeight,
    };
  });
}

/** Holds downloaded application scripts while allowing the head bootstrap and CSS. */
async function pauseHydration(page: Page) {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(/\/_next\/.*\.js(?:\?|$)/, async route => {
    await gate;
    await route.continue();
  });
  return release;
}

for (const width of [320, 390, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`preserves first-paint geometry at ${width}px in ${theme} mode`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.addInitScript(value => {
        localStorage.setItem('areqa:interface-theme', value);
        localStorage.setItem('areqa:interface-language', 'en');
      }, theme);
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      const release = await pauseHydration(page);
      try {
        await page.goto('/', { waitUntil: 'commit' });
        await expect(page.locator('.areqa-chat-input-shell')).toHaveCSS('border-radius', '999px');
        const before = await geometry(page);
        expect(before.background).toBe(theme === 'light' ? 'rgb(255, 255, 255)' : 'rgb(36, 36, 36)');
        expect(before.toggleX).toBe(width <= 768 ? 16 : 228);
        release();
        await page.waitForFunction(() => document.querySelector('textarea')?.style.height === '22px');
        expect(await geometry(page)).toEqual(before);
        expect(errors).toEqual([]);
        await expect(page.locator('textarea')).toHaveCSS('overflow-y', 'hidden');

        // The Next.js development indicator can overlap the actual account controls.
        await page.locator('nextjs-portal').evaluateAll(elements => elements.forEach(el => {
          (el as HTMLElement).style.display = 'none';
        }));
        const toggle = page.locator('.areqa-chat-sidebar-toggle');
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', width <= 768 ? 'true' : 'false');
        // Measure the anchor, since the button intentionally scales while pressed.
        expect(await page.locator('.areqa-chat-sidebar-floating-action').evaluate(el => el.getBoundingClientRect().x))
          .toBe(width <= 768 ? Math.min(280, width - 48) - 52 : 16);
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', width <= 768 ? 'false' : 'true');

        const input = page.locator('textarea');
        await input.fill(Array.from({ length: 20 }, (_, index) => `Line ${index}`).join('\n'));
        await expect(input).toHaveCSS('height', '200px');
        await expect(input).toHaveCSS('overflow-y', 'auto');
        expect(await input.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
        await input.fill('short');
        await expect(input).toHaveCSS('height', '22px');
        await expect(input).toHaveCSS('overflow-y', 'hidden');
      } finally { release(); }
    });
  }
}

test('migrates a legacy Chinese preference without a hydration error and renders it on reload', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem('areqa:interface-theme', 'light');
    localStorage.setItem('areqa:interface-language', 'zh-TW');
  });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('textarea')).toHaveAttribute('aria-label', '訊息輸入框');
  await expect.poll(async () => (await page.context().cookies()).find(c => c.name === 'areqa_interface_language')?.value).toBe('zh-TW');
  const release = await pauseHydration(page);
  try {
    await page.reload({ waitUntil: 'commit' });
    await expect(page.locator('textarea')).toHaveAttribute('aria-label', '訊息輸入框');
    await expect(page.locator('.areqa-chat-input-shell')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
    release();
    await page.waitForFunction(() => document.querySelector('textarea')?.style.height === '22px');
    expect(errors).toEqual([]);
  } finally { release(); }
});

test('uses server cookie preferences when browser storage is denied', async ({ page, baseURL }) => {
  await page.context().addCookies([
    { name: 'areqa_interface_theme', value: 'light', url: baseURL! },
    { name: 'areqa_interface_language', value: 'zh-TW', url: baseURL! },
  ]);
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get: () => { throw new Error('storage denied'); } });
  });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('textarea')).toHaveAttribute('aria-label', '訊息輸入框');
  await expect(page.locator('html')).toHaveAttribute('data-interface-theme', 'light');
  await page.waitForFunction(() => document.querySelector('textarea')?.style.height === '22px');
  expect(errors).toEqual([]);
});

test('remeasures an unchanged draft when its width or font changes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.waitForFunction(() => document.querySelector('textarea')?.style.height === '22px');
  const input = page.locator('textarea');
  const draft = 'Socratic tutoring '.repeat(10);
  await input.fill(draft);
  const narrowHeight = await input.evaluate(el => el.clientHeight);
  await page.setViewportSize({ width: 600, height: 844 });
  await expect.poll(() => input.evaluate(el => el.clientHeight)).toBeLessThan(narrowHeight);
  const wideHeight = await input.evaluate(el => el.clientHeight);
  await input.evaluate(el => {
    el.style.fontSize = '24px';
    el.style.lineHeight = '30px';
    document.fonts.dispatchEvent(new Event('loadingdone'));
  });
  await expect.poll(() => input.evaluate(el => el.clientHeight)).toBeGreaterThan(wideHeight);
  await expect(input).toHaveValue(draft);
});
