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
      const current = cards.get(id) ?? { stage: 1, version: 0, card: empty, pending: null, history: [] };
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
    return route.fulfill({ json: cards.get(id) ?? { stage: 1, version: 0, card: empty, pending: null, history: [] } });
  });
  // Adopting merges the draft and adds a version; the stage never changes here.
  await page.route('**/api/research-coach/*/confirm', (route) => {
    const id = route.request().url().split('/research-coach/')[1].split('/')[0];
    const current = cards.get(id) ?? { stage: 1, version: 0, card: empty, pending: null, history: [] };
    const { version } = route.request().postDataJSON();
    if (version !== current.version || !current.pending) return route.fulfill({ json: { adopted: false, state: current } });
    const next: Card = {
      stage: current.stage, version: current.version + 1, card: current.pending.card, pending: null,
      history: [...current.history, { version: current.version + 1, stage: current.stage, note: current.pending.notes.join('；'), confirmed_at: 1 }],
    };
    cards.set(id, next);
    return route.fulfill({ json: { adopted: true, state: next } });
  });
  // Declining drops the draft; the adopted card and version stay.
  await page.route('**/api/research-coach/*/reject', (route) => {
    const id = route.request().url().split('/research-coach/')[1].split('/')[0];
    const current = cards.get(id) ?? { stage: 1, version: 0, card: empty, pending: null, history: [] };
    const { version } = route.request().postDataJSON();
    if (version !== current.version || !current.pending) return route.fulfill({ json: { rejected: false, state: current } });
    const next: Card = { ...current, pending: null };
    cards.set(id, next);
    return route.fulfill({ json: { rejected: true, state: next } });
  });
  // The learner picks any stage.
  await page.route('**/api/research-coach/*/stage', (route) => {
    const id = route.request().url().split('/research-coach/')[1].split('/')[0];
    const current = cards.get(id) ?? { stage: 1, version: 0, card: empty, pending: null, history: [] };
    const next = { ...current, stage: route.request().postDataJSON().stage };
    cards.set(id, next);
    return route.fulfill({ json: next });
  });
  return { streamRequests };
}

async function send(page: Page, content: string) {
  await page.getByLabel('訊息輸入框').fill(content);
  await page.getByRole('button', { name: '發送訊息', exact: true }).click();
}

async function startTopicFinder(page: Page) {
  await page.getByRole('button', { name: '選題：找出適合你的研究題目' }).first().click();
  await expect(page.getByRole('button', { name: '選題 測試版', exact: true })).toHaveAttribute('aria-pressed', 'true');
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
  await expect(page.getByRole('button', { name: '選題 測試版', exact: true })).toHaveCount(0);
  await expect(page.locator('.areqa-topic-finder-badge')).toBeVisible();
  expect(streamRequests[0]).toMatchObject({ conversation_kind: 'research_coach', tutor_profile: 'general' });
  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('上傳檔案')).toBeVisible();
  await expect(page.getByText('Create Image')).toHaveCount(0);
  await expect(page.getByText('English Tutor')).toHaveCount(0);
});

test('@smoke the topic card adopts drafts, jumps between stages, and survives a reload', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  const card = page.getByRole('region', { name: '題目卡' });
  await expect(card.getByRole('group', { name: /目前的題目/ })).toContainText('系統和 Gemini 差不多', { timeout: 15_000 });
  await expect(card.getByText('版本 v0')).toBeVisible();

  await card.getByRole('button', { name: '需要', exact: true }).click();
  await expect(card.getByText('版本 v1')).toBeVisible();
  await expect(card.locator('.areqa-topic-card-step-label')).toHaveText('第 1 階段');

  // Jump straight to stage 4, then back to stage 2.
  await card.getByRole('button', { name: '切換到第 4 階段：幫候選題目找「看得見的證據」' }).click();
  await expect(card.getByRole('heading', { name: '幫候選題目找「看得見的證據」' })).toBeVisible();
  await expect(page.locator('.areqa-topic-finder-badge')).toContainText('第 4 階段');
  await card.getByRole('button', { name: '切換到第 2 階段：有沒有很簡單的解法？' }).click();
  await expect(card.getByRole('heading', { name: '有沒有很簡單的解法？' })).toBeVisible();
  await card.getByRole('button', { name: '下一階段 →' }).click();
  await expect(card.locator('.areqa-topic-card-step-label')).toHaveText('第 3 階段');

  await page.reload();
  await page.locator('.areqa-conversation-item').first().click();
  await expect(page.getByRole('region', { name: '題目卡' }).getByText('版本 v1')).toBeVisible();
  await expect(page.getByRole('region', { name: '題目卡' }).getByText('系統和 Gemini 差不多')).toBeVisible();
});

test('@smoke the coach focus can be set aside and a revision shows the check-back', async ({ page }) => {
  await mockBackend(page);
  const measures = [{ term: '篩選能力', measure: '' }, { term: '使用頻率', measure: '' }];
  const card = { ...empty, mother_question: '工具代勞會不會削弱篩選能力', operationalization: measures };
  const revised = { ...card, mother_question: '人還會發展自己的篩選能力嗎' };
  const focuses = [
    { id: 'measure:aaaaaaaaaaaa', kind: 'measure', term: '篩選能力' },
    { id: 'measure:bbbbbbbbbbbb', kind: 'measure', term: '使用頻率' },
  ];
  const skipped: string[] = [];
  let state: Record<string, unknown> = {
    stage: 4, version: 2, card, pending: { card: revised, notes: ['母問題往上抽一層'] }, history: [], focus: focuses[0],
  };
  // Routes registered later take precedence over the generic fake backend.
  await page.route('**/api/research-coach/*/card', (route) => route.fulfill({ json: state }));
  await page.route('**/api/research-coach/*/focus', (route) => {
    skipped.push(route.request().postDataJSON().gap_id);
    state = { ...state, skipped_focus: [...skipped], focus: focuses.find((focus) => !skipped.includes(focus.id)) ?? null };
    return route.fulfill({ json: state });
  });
  await page.route('**/api/research-coach/*/confirm', (route) => {
    state = {
      ...state, version: 3, card: revised, pending: null, focus: null,
      review: { version: 3, changed: ['mother_question'], stages: [2, 5], created_at: 1 },
    };
    return route.fulfill({ json: { adopted: true, state } });
  });

  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我想把問題往上抽一層');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  const region = page.getByRole('region', { name: '題目卡' });
  await expect(region.getByText('這輪先看：「篩選能力」要用什麼證據看出來')).toBeVisible({ timeout: 15_000 });
  await region.getByRole('button', { name: '換一個' }).click();
  await expect(region.getByText('這輪先看：「使用頻率」要用什麼證據看出來')).toBeVisible();
  expect(skipped).toEqual(['measure:aaaaaaaaaaaa']);

  await region.getByRole('button', { name: '需要', exact: true }).click();
  await expect(region.getByText('你剛改了題目，教練下一輪會先陪你回頭看第 2、5 階段還成不成立。')).toBeVisible();
  await expect(region.getByRole('button', { name: '換一個' })).toHaveCount(0);
});

test('@smoke the draft asks one question and 不需要 clears it without a new version', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  const card = page.getByRole('region', { name: '題目卡' });
  const draft = card.getByRole('group', { name: 'AI 幫你整理了以下內容，要更新到下方「目前的題目」嗎？' });
  await expect(draft).toContainText('回覆策略與反思', { timeout: 15_000 });
  await expect(draft.getByRole('button', { name: '需要', exact: true })).toBeVisible();
  await expect(card.getByRole('button', { name: '我再想想' })).toHaveCount(0);

  await draft.getByRole('button', { name: '不需要', exact: true }).click();
  await expect(draft).toHaveCount(0);
  await expect(card.getByText('版本 v0')).toBeVisible();
  await expect(card.getByText('回覆策略與反思')).toHaveCount(0);
});

test('@smoke the chat nudge moves to the next stage as a learner message', async ({ page }) => {
  const { streamRequests } = await mockBackend(page);
  const card = { ...empty, mother_question: '學生願不願意接受 AI 先分流？' };
  let state: Record<string, unknown> = { stage: 3, version: 2, card, pending: null, history: [], next_stage: null };
  await page.route('**/api/research-coach/*/card', (route) => route.fulfill({ json: state }));

  await page.goto('/');
  await startTopicFinder(page);
  await send(page, '我的母問題是：學生願不願意接受 AI 先分流？');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  // The learner adopted the mother question; the card now covers stage 3.
  state = { ...state, next_stage: 4 };
  const nudge = page.getByRole('button', { name: '前往第 4 階段：幫候選題目找「看得見的證據」' });
  await expect(nudge).toBeVisible({ timeout: 15_000 });
  // The backend applies the explicit request before answering.
  state = { ...state, stage: 4, next_stage: null };
  await nudge.click();

  await expect(page.getByText('回覆第2輪', { exact: true })).toBeVisible();
  expect(streamRequests[1].messages.at(-1)?.content).toBe('好，我們進到第 4 階段：幫候選題目找「看得見的證據」');
  await expect(page.locator('.areqa-topic-finder-badge')).toContainText('第 4 階段', { timeout: 15_000 });
  await expect(page.getByRole('button', { name: /前往第/ })).toHaveCount(0);
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

  // Candidates become explorable once the learner adopts the draft.
  await card.getByRole('button', { name: '需要', exact: true }).click();
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
  await page.getByRole('button', { name: '選題 測試版', exact: true }).click();
  await send(page, '我做的系統和 Gemini 差不多');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  await page.locator('.areqa-topic-finder-badge').click();
  const card = page.getByRole('region', { name: '題目卡' });
  await expect(card).toBeVisible();
  await expect(card.getByRole('button', { name: '需要', exact: true })).toBeVisible();
  await expect(card.getByRole('button', { name: '不需要', exact: true })).toBeVisible();
  await expect(card.getByRole('button', { name: '切換到第 5 階段：做得到嗎？' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('@smoke the first visit to Topic Finder walks through a short tour, once', async ({ page }) => {
  await page.route('**/api/chat', (route) => route.fulfill({
    contentType: 'text/event-stream',
    body: `data: ${JSON.stringify({ choices: [{ delta: { content: '先說說你最在乎的是哪個部分？' } }] })}\n\ndata: [DONE]\n\n`,
  }));
  await page.route('**/api/title', (route) => route.fulfill({ contentType: 'text/event-stream', body: 'data: [DONE]\n\n' }));
  await page.route('**/api/research-coach/*/card', (route) => route.fulfill({ json: { stage: 1, version: 0, card: empty, pending: null, history: [] } }));
  await page.goto('/');
  // The first-run tour of the whole app is a separate tour; dismiss it.
  await page.getByRole('button', { name: '略過引導' }).click();

  await page.getByRole('button', { name: '選題：找出適合你的研究題目' }).first().click();
  await expect(page.getByText('歡迎來到選題')).toBeVisible();
  // The five stages render as a numbered list (Tailwind's preflight would otherwise hide the markers).
  const stageList = page.locator('.ant-tour ol').first();
  await expect(stageList.locator('li')).toHaveCount(5);
  expect(await stageList.evaluate((element) => getComputedStyle(element).listStyleType)).toBe('decimal');
  await page.getByRole('button', { name: '開始（約 30 秒）' }).click();

  await expect(page.getByText('先說說你的痛點')).toBeVisible();
  await page.getByRole('button', { name: '我好奇 AI 的回答方式會不會讓學生想得更少' }).click();
  await expect(page.getByText('先說說你最在乎的是哪個部分？', { exact: true })).toBeVisible();

  await expect(page.getByText('這是你的題目卡')).toBeVisible({ timeout: 15_000 });
  const cardPoints = page.locator('.ant-tour ul').first();
  await expect(cardPoints.locator('li')).toHaveCount(4);
  expect(await cardPoints.evaluate((element) => getComputedStyle(element).listStyleType)).toBe('disc');
  await expect(cardPoints).toContainText('AI 提議');
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
    const option = page.getByRole('button', { name: 'Topic Finder Beta', exact: true });
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
