import { resolve } from 'node:path';
import { test, expect } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import type { Page, APIRequestContext } from '../../../frontend/node_modules/@playwright/test';

async function scenario(request: APIRequestContext, name: string) {
  expect((await request.post('/__test/scenario', { data: { scenario: name } })).ok()).toBe(true);
}
async function send(page: Page, content: string) {
  await page.getByLabel('訊息輸入框').fill(content);
  await page.getByLabel('發送訊息', { exact: true }).click();
}
async function idle(page: Page) {
  await expect(page.getByLabel('停止生成', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('訊息輸入框')).toBeEnabled();
}
async function firstTurn(page: Page, request: APIRequestContext) {
  await scenario(request, 'text');
  await page.goto('/');
  await send(page, '請解釋效果量');
  await expect(page.getByText('一般文字回答', { exact: true })).toBeVisible();
  await idle(page);
}

for (const kind of ['pdf', 'txt', 'md', 'png'] as const) {
  test(`@smoke second-turn ${kind} attachment produces a persisted answer and permits follow-up`, async ({ page, request }) => {
    await firstTurn(page, request);
    await scenario(request, 'context_ok');
    const buffer = kind === 'pdf'
      ? await (await request.get('/__test/document.pdf')).body()
      : kind === 'png' ? await (await request.get('/__test/image.png')).body()
        : Buffer.from('A'.repeat(52_000) + 'ATTACHMENT_END_MARKER');
    const mimeType = { pdf: 'application/pdf', txt: 'text/plain', md: 'text/markdown', png: 'image/png' }[kind]!;
    await page.getByLabel('選擇附件').setInputFiles({ name: `source.${kind}`, mimeType, buffer });
    await send(page, '請摘要附件並保留研究指標');
    await expect(page.getByText('附件分析完成', { exact: true })).toBeVisible();
    await idle(page);
    const state = await (await request.get('/__test/state')).json();
    expect(state.main_calls).toBe(1);
    expect(kind === 'txt' || kind === 'md' ? state.tail_preserved : state.native_attachment).toEqual([true]);
    await page.reload();
    await expect(page.getByText('一般文字回答', { exact: true })).toBeVisible();
    await expect(page.getByText('附件分析完成', { exact: true })).toBeVisible();
    await send(page, '請繼續說明');
    await expect(page.getByText('附件分析完成', { exact: true })).toHaveCount(2);
    await idle(page);
    await expect(page.getByText('部分較早對話暫時無法完整納入本次回答', { exact: false })).toHaveCount(0);
  });
}

for (const [name, attempts, answer] of [
  ['context_retry', 2, '附件分析完成'],
  ['context_repeat', 2, '模型仍無法容納'],
  ['context_partial', 1, '部分回答'],
  ['context_rate_limit', 1, '生成回答時發生錯誤'],
] as const) {
  test(`${name}: bounded recovery finishes the UI and preserves the current attachment`, async ({ page, request }) => {
    await firstTurn(page, request);
    await scenario(request, name);
    await page.getByLabel('選擇附件').setInputFiles({ name: 'source.txt', mimeType: 'text/plain', buffer: Buffer.from('ATTACHMENT_END_MARKER') });
    await send(page, '請分析附件');
    await expect(page.getByText(answer, { exact: false })).toBeVisible();
    await idle(page);
    const state = await (await request.get('/__test/state')).json();
    expect(state.main_calls).toBe(attempts);
    expect(state.tail_preserved).toEqual(Array(attempts).fill(true));
    if (attempts === 2) expect(state.message_counts[1]).toBeLessThan(state.message_counts[0]);
    if (name === 'context_partial') await expect(page.getByText('模型仍無法容納', { exact: false })).toBeVisible();
    await scenario(request, 'context_ok');
    await send(page, '請繼續回答');
    await expect(page.getByText('附件分析完成', { exact: true })).toHaveCount(name === 'context_retry' ? 2 : 1);
    await idle(page);
  });
}

test('@smoke attachment above the old allowance reaches the model and permits the next turn', async ({ page, request }) => {
  await firstTurn(page, request);
  await scenario(request, 'context_ok');
  await page.getByLabel('選擇附件').setInputFiles({ name: 'large.txt', mimeType: 'text/plain', buffer: Buffer.from('A'.repeat(140_000) + 'ATTACHMENT_END_MARKER') });
  await send(page, '請摘要附件');
  await expect(page.getByText('附件分析完成', { exact: true })).toBeVisible();
  await idle(page);
  expect((await (await request.get('/__test/state')).json()).main_calls).toBe(1);
  expect((await (await request.get('/__test/state')).json()).tail_preserved).toEqual([true]);
  await send(page, '請說明效果量');
  await expect(page.getByText('附件分析完成', { exact: true })).toHaveCount(2);
  await idle(page);
});

test('HTTP multipart accepts more than 100 history messages and emits one terminal event', async ({ request }) => {
  await scenario(request, 'context_ok');
  const messages = Array.from({ length: 100 }, (_, index) => ({
    role: index % 2 === 0 ? 'user' : 'assistant', content: `研究指標 ${index}`,
  }));
  messages.push({ role: 'user', content: '請根據附件繼續整理研究指標' });
  const response = await request.post('/api/chat', {
    multipart: {
      messages: JSON.stringify({ messages, conversation_id: 'context-http-history', search_mode: 'never', use_web_search: false }),
      attachments: { name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from('A'.repeat(52_000) + 'ATTACHMENT_END_MARKER') },
    },
  });
  expect(response.ok()).toBe(true);
  expect(response.headers()['content-type']).toContain('text/event-stream');
  const body = await response.text();
  expect(body).toContain('附件分析完成');
  expect(body.match(/data: \[DONE\]/g)).toHaveLength(1);
  expect(body).not.toContain('超過');
  const state = await (await request.get('/__test/state')).json();
  expect(state.main_calls).toBe(1);
  expect(state.tail_preserved).toEqual([true]);
});


test('@smoke A-MEM paper reaches the answer model through file upload', async ({ page, request }) => {
  await firstTurn(page, request);
  await scenario(request, 'context_ok');
  await page.getByLabel('選擇附件').setInputFiles(resolve('docs/paper/memory_work/A-MEM_Agentic Memory for LLM Agents.pdf'));
  await send(page, '請解釋這篇論文的研究問題、方法、主要結果與限制');
  await expect(page.getByText('附件分析完成', { exact: true })).toBeVisible();
  await idle(page);
  const state = await (await request.get('/__test/state')).json();
  expect(state.main_calls).toBe(1);
  expect(state.native_attachment).toEqual([true]);
  await expect(page.getByText('超過本次可閱讀容量', { exact: false })).toHaveCount(0);
});
