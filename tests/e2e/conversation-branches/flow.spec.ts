import { expect, test, type Page } from '../../../frontend/node_modules/@playwright/test/index.mjs';

async function send(page: Page, content: string) {
  await page.getByLabel('訊息輸入框').fill(content);
  await page.getByRole('button', { name: '發送訊息', exact: true }).click();
}

test('@smoke branches an ordinary chat, sends only its history, and reloads it', async ({ page }) => {
  const requests: Array<{ conversation_id: string; isolated_context: boolean; messages: Array<{ content: string }> }> = [];
  const replies = ['第一輪回覆', '來源對話的第二輪回覆', '分支專屬回覆'];
  await page.route('**/api/chat', async route => {
    const request = route.request().postDataJSON();
    const reply = replies[requests.length];
    requests.push(request);
    await route.fulfill({
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({ choices: [{ delta: { content: reply } }] })}\n\n`,
        'data: [DONE]\n\n',
      ].join(''),
    });
  });
  await page.route('**/api/title', route => route.fulfill({
    contentType: 'text/event-stream',
    body: 'data: {"content":"分支測試來源"}\n\ndata: [DONE]\n\n',
  }));

  await page.goto('/');
  await send(page, '第一輪問題');
  await expect(page.getByText('第一輪回覆', { exact: true })).toBeVisible();
  await send(page, '只有來源對話有這個問題');
  await expect(page.getByText('來源對話的第二輪回覆', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '更多回覆操作', exact: true }).first().click();
  await page.getByRole('menuitem', { name: '建立新對話分支', exact: true }).click();
  const toBranch = page.getByRole('button', { name: /^到分支 · / });
  await expect(toBranch).toBeVisible();
  await expect(page.getByText('只有來源對話有這個問題', { exact: true })).toBeVisible();
  const sourceReply = page.getByText('第一輪回覆', { exact: true });
  const firstReplyId = await sourceReply.evaluate(reply => reply.closest('[data-message-id]')?.getAttribute('data-message-id'));
  expect(firstReplyId).toBeTruthy();
  expect(requests).toHaveLength(2);

  await toBranch.click();
  const fromSource = page.getByRole('button', { name: '從 · 分支測試來源', exact: true });
  await expect(fromSource).toBeVisible();
  await expect(page.getByText('第一輪回覆', { exact: true })).toBeVisible();
  await expect(page.getByText('只有來源對話有這個問題', { exact: true })).toHaveCount(0);

  await send(page, '分支的新問題');
  await expect(page.getByText('分支專屬回覆', { exact: true })).toBeVisible();
  expect(requests[2].conversation_id).not.toBe(requests[0].conversation_id);
  expect(requests[0].isolated_context).toBe(false);
  expect(requests[2].isolated_context).toBe(true);
  expect(requests[2].messages.map(({ content }) => content)).toEqual([
    '第一輪問題', '第一輪回覆', '分支的新問題',
  ]);

  await page.reload();
  await page.getByText(/^分支 · /).click();
  await expect(page.getByText('分支專屬回覆', { exact: true })).toBeVisible();
  await expect(page.getByText('只有來源對話有這個問題', { exact: true })).toHaveCount(0);
  await fromSource.click();
  await expect(page.getByText('來源對話的第二輪回覆', { exact: true })).toBeVisible();
  await expect(page.getByText('分支專屬回覆', { exact: true })).toHaveCount(0);
  await expect(page.locator(`[data-message-id="${firstReplyId}"]`)).toBeInViewport();
});
