import { expect, test, type Page } from '../../../frontend/node_modules/@playwright/test/index.mjs';

type Card = {
  stage: number;
  version: number;
  card: Record<string, unknown>;
  pending: { card: Record<string, unknown>; notes: string[] } | null;
  history: Array<{ version: number; stage: number; note: string; confirmed_at: number }>;
};

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
const proposal = { ...empty, pain_point: '系統和 Gemini 差不多', candidates: ['回覆策略與反思', '提問與講解的平衡'] };

/** Fake backend: chat stream, titles, and per-conversation topic cards that survive reloads. */
async function mockBackend(page: Page) {
  const streamRequests: Array<Record<string, unknown> & { messages: Array<{ content: string }> }> = [];
  const cards = new Map<string, Card>();
  await page.addLocatorHandler(page.getByRole('button', { name: '略過引導' }), async (button) => { await button.click(); });
  await page.route('**/api/chat', async (route) => {
    const body = route.request().postDataJSON();
    streamRequests.push(body);
    const id = String(body.conversation_id);
    // After a Topic Finder answer the backend proposes a draft; it never advances the stage itself.
    if (body.conversation_kind === 'research_coach') {
      const current = cards.get(id) ?? { stage: 0, version: 0, card: empty, pending: null, history: [] };
      cards.set(id, { ...current, pending: { card: proposal, notes: ['加入痛點與候選題目'] } });
    }
    await route.fulfill({
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ choices: [{ delta: { content: `回覆第${streamRequests.length}輪` } }] })}\n\ndata: [DONE]\n\n`,
    });
  });
  await page.route('**/api/title', (route) => route.fulfill({
    contentType: 'text/event-stream', body: 'data: {"content":"選題測試"}\n\ndata: [DONE]\n\n',
  }));
  await page.route('**/api/research-coach/*/card', (route) => {
    const id = route.request().url().split('/research-coach/')[1].split('/')[0];
    return route.fulfill({ json: cards.get(id) ?? { stage: 0, version: 0, card: empty, pending: null, history: [] } });
  });
  await page.route('**/api/research-coach/*/confirm', (route) => {
    const id = route.request().url().split('/research-coach/')[1].split('/')[0];
    const current = cards.get(id) ?? { stage: 0, version: 0, card: empty, pending: null, history: [] };
    const { version } = route.request().postDataJSON();
    if (version !== current.version) return route.fulfill({ json: { advanced: false, state: current } });
    const next: Card = {
      stage: current.stage + 1, version: current.version + 1, card: current.pending?.card ?? current.card, pending: null,
      history: [...current.history, { version: current.version + 1, stage: current.stage + 1, note: current.pending?.notes.join('；') ?? '', confirmed_at: 1 }],
    };
    cards.set(id, next);
    return route.fulfill({ json: { advanced: true, state: next } });
  });
  return { streamRequests };
}

async function send(page: Page, content: string) {
  await page.getByLabel('訊息輸入框').fill(content);
  await page.getByRole('button', { name: '發送訊息', exact: true }).click();
}

async function startTopicFinder(page: Page) {
  await page.getByRole('button', { name: '選題：找出適合你的研究題目' }).first().click();
  await expect(page.getByRole('button', { name: '選題', exact: true })).toHaveAttribute('aria-pressed', 'true');
}

test('@smoke switching to Topic Finder shows its home with the top switch', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: '對話', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await startTopicFinder(page);

  await expect(page.getByLabel('訊息輸入框')).toHaveAttribute('placeholder', '說說你最近卡住的問題……');
  const slot = await page.locator('.areqa-workspace-switch-home-slot').boundingBox();
  expect(slot && slot.y).toBeGreaterThanOrEqual(12);
  expect(slot && slot.y).toBeLessThan(40);
});

test('@smoke the first Topic Finder message streams, hides the switch, and shows the badge', async ({ page }) => {
  const { streamRequests } = await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);

  await send(page, '我做的系統和 Gemini 差不多');

  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '選題', exact: true })).toHaveCount(0);
  await expect(page.locator('.areqa-topic-finder-badge')).toBeVisible();
  expect(streamRequests[0]).toMatchObject({ conversation_kind: 'research_coach', tutor_profile: 'general' });
  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('上傳檔案')).toBeVisible();
  await expect(page.getByText('Create Image')).toHaveCount(0);
  await expect(page.getByText('English Tutor')).toHaveCount(0);
});

test('@smoke the topic card loads, advances only on confirm, and survives a reload', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  const card = page.getByRole('region', { name: '題目卡' });
  await expect(card.getByRole('note')).toContainText('加入痛點與候選題目', { timeout: 15_000 });
  await expect(card.getByText('版本 v0')).toBeVisible();

  await card.getByRole('button', { name: '我確認這一關過了' }).click();
  await expect(card.getByText('版本 v1')).toBeVisible();
  await expect(card.locator('li[aria-current="step"]')).toContainText('時間');
  await expect(page.locator('.areqa-topic-finder-badge')).toContainText('篩子 1/5：時間');

  await page.reload();
  await page.locator('.areqa-conversation-item').first().click();
  await expect(page.getByRole('region', { name: '題目卡' }).getByText('版本 v1')).toBeVisible();
  await expect(page.getByRole('region', { name: '題目卡' }).getByText('系統和 Gemini 差不多')).toBeVisible();
});

test('@smoke Chat stays separate and ordinary chat still works', async ({ page }) => {
  const { streamRequests } = await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '選題用的痛點');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();
  const topicId = String(streamRequests[0].conversation_id);

  await page.getByRole('button', { name: '一般對話' }).click();
  await expect(page.locator(`[data-conversation-id="${topicId}"]`)).toHaveCount(0);
  await send(page, '一般問題');
  await expect(page.getByText('回覆第2輪', { exact: true })).toBeVisible();
  expect(streamRequests[1]).toMatchObject({ conversation_kind: 'chat' });
  await expect(page.locator('.areqa-topic-finder-badge')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '題目卡' })).toHaveCount(0);
});

test('@smoke a candidate branch stays in Topic Finder and the card exports as Markdown', async ({ page }) => {
  const { streamRequests } = await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();
  const card = page.getByRole('region', { name: '題目卡' });
  await expect(card.getByText('提問與講解的平衡')).toBeVisible({ timeout: 15_000 });

  const download = page.waitForEvent('download');
  await card.getByRole('button', { name: '匯出 Markdown' }).click();
  expect((await download).suggestedFilename()).toBe('areqa-topic-card-v0.md');

  await card.getByRole('button', { name: '開分支探索：提問與講解的平衡' }).click();
  await expect(page.getByText('回覆第2輪', { exact: true })).toBeVisible();
  expect(streamRequests[1]).toMatchObject({ conversation_kind: 'research_coach', isolated_context: true });
  expect(streamRequests[1].messages.at(-1)?.content).toContain('提問與講解的平衡');
  await expect(page.getByText('候選 · 提問與講解的平衡')).toBeVisible();

  await page.getByRole('button', { name: '一般對話' }).click();
  await expect(page.getByText('候選 · 提問與講解的平衡')).toHaveCount(0);
});

test('@smoke on a phone the topic card opens as a drawer without horizontal scroll', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockBackend(page);
  await page.goto('/');
  await page.getByRole('button', { name: '選題', exact: true }).click();
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  await page.locator('.areqa-topic-finder-badge').click();
  const card = page.getByRole('region', { name: '題目卡' });
  await expect(card).toBeVisible();
  await expect(card.getByRole('button', { name: '我確認這一關過了' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('@smoke the first visit to Topic Finder walks through a short tour, once', async ({ page }) => {
  await page.route('**/api/chat', (route) => route.fulfill({
    contentType: 'text/event-stream',
    body: `data: ${JSON.stringify({ choices: [{ delta: { content: '先說說你最在乎的是哪個部分？' } }] })}\n\ndata: [DONE]\n\n`,
  }));
  await page.route('**/api/title', (route) => route.fulfill({ contentType: 'text/event-stream', body: 'data: [DONE]\n\n' }));
  await page.route('**/api/research-coach/*/card', (route) => route.fulfill({ json: { stage: 0, version: 0, card: empty, pending: null, history: [] } }));
  await page.goto('/');
  // The first-run tour of the whole app is a separate tour; dismiss it.
  await page.getByRole('button', { name: '略過引導' }).click();

  await page.getByRole('button', { name: '選題：找出適合你的研究題目' }).first().click();
  await expect(page.getByText('歡迎來到選題')).toBeVisible();
  await page.getByRole('button', { name: '開始（約 30 秒）' }).click();

  await expect(page.getByText('先說說你的痛點')).toBeVisible();
  await page.getByRole('button', { name: '我好奇 AI 的回答方式會不會讓學生想得更少' }).click();
  await expect(page.getByText('先說說你最在乎的是哪個部分？', { exact: true })).toBeVisible();

  await expect(page.getByText('這是你的題目卡')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /^下一步/ }).click();
  await expect(page.getByText('準備好了')).toBeVisible();
  await page.getByRole('button', { name: /^完成/ }).click();
  await expect(page.getByText('準備好了')).toHaveCount(0);

  await page.reload();
  await page.getByRole('button', { name: '略過引導' }).click({ timeout: 5_000 }).catch(() => undefined);
  await page.getByRole('button', { name: '一般對話' }).click();
  await page.getByRole('button', { name: '選題：找出適合你的研究題目' }).first().click();
  await expect(page.getByText('歡迎來到選題')).toHaveCount(0);
});

test('@smoke English labels fit: one-line switch and wrapped tour examples', async ({ page }) => {
  // The harness pins zh-TW; keep English for this check only.
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    localStorage.setItem('areqa:interface-language', 'en');
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key === 'areqa:interface-language') return;
      return original.call(this, key, value);
    };
  });
  for (const width of [918, 390]) {
    await page.setViewportSize({ width, height: 760 });
    await page.goto('/');
    // Each width starts from Chat with the Topic Finder tour not yet seen.
    await page.evaluate(() => Object.keys(localStorage)
      .filter((key) => key.startsWith('areqa:topic-finder-tour') || key === 'areqa:workspace')
      .forEach((key) => localStorage.removeItem(key)));
    await page.reload();
    // The app-wide first-run tour shows only once; skip it if it is there.
    const skipAppTour = page.getByRole('button', { name: 'Skip tour' });
    await skipAppTour.waitFor({ timeout: 3_000 }).then(() => skipAppTour.click()).catch(() => undefined);
    const option = page.getByRole('button', { name: 'Topic Finder', exact: true });
    expect((await option.boundingBox())!.height).toBeLessThan(40);
    await option.click();
    await page.getByRole('button', { name: 'Start (about 30 seconds)' }).click();
    await expect(page.getByText('Start with your pain point')).toBeVisible();
    const fits = await page.evaluate(() => {
      const popup = document.querySelector('.ant-tour') as HTMLElement;
      const box = popup.getBoundingClientRect();
      return [...popup.querySelectorAll('.ant-btn')].every((button) => {
        const rect = button.getBoundingClientRect();
        return rect.left >= box.left - 1 && rect.right <= box.right + 1;
      });
    });
    expect(fits).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  }
});

test('@smoke the Topic Finder tour still appears after the app tour is dismissed', async ({ page }) => {
  // A new account that lands in Topic Finder sees the app tour first.
  await page.addInitScript(() => localStorage.setItem('areqa:workspace', 'research_coach'));
  await page.goto('/');
  await page.getByRole('button', { name: '略過引導' }).click();
  await expect(page.getByText('歡迎來到選題')).toBeVisible();
});
