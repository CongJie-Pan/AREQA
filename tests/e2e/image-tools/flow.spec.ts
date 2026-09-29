import { test, expect } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import type { Page, APIRequestContext } from '../../../frontend/node_modules/@playwright/test';

async function scenario(request: APIRequestContext, name: string) {
  await request.post('/__test/scenario', { data: { scenario: name } });
}
async function send(page: Page, content: string) {
  await page.getByLabel('訊息輸入框').fill(content);
  await page.getByLabel('發送訊息', { exact: true }).click();
}

test('ordinary chat bypasses image classification and attachment-only sends remain text', async ({ page, request }) => {
  const urls: string[] = [];
  page.on('request', (req) => urls.push(req.url()));
  await scenario(request, 'text');
  await page.goto('/');
  await send(page, '請解釋效果量');
  await expect(page.getByText('一般文字回答', { exact: true })).toBeVisible();
  await scenario(request, 'attachment');
  await page.getByLabel('選擇附件').setInputFiles({ name: 'source.txt', mimeType: 'text/plain', buffer: Buffer.from('Sample size and effect size.') });
  await page.getByLabel('發送訊息', { exact: true }).click();
  await expect(page.getByText('附件分析完成', { exact: true })).toBeVisible();
  await page.getByLabel('選擇附件').setInputFiles({ name: 'source.txt', mimeType: 'text/plain', buffer: Buffer.from('Sample size and effect size.') });
  await send(page, '你好');
  await expect(page.getByText('附件分析完成', { exact: true })).toHaveCount(2);
  const state = await (await request.get('/__test/state')).json();
  expect(state.generated).toBe(0);
  expect(state.references).toBe(0);
  expect(state.uploads).toBeGreaterThan(0);
  expect(urls.some((url) => url.includes('/images/intent'))).toBe(false);
});

test('mixed analysis and image survive loading, completion and IndexedDB history', async ({ page, request }) => {
  await scenario(request, 'mixed');
  await page.goto('/');
  await send(page, '請先分析，再依內容製作教學圖');
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect(page.getByRole('status', { name: '圖片產生中' })).toBeVisible();
  await expect(page.getByLabel('停止生成', { exact: true })).toBeVisible();
  await expect(page.getByAltText('效果量教學圖')).toBeVisible();
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(async () => (window as any).imageTest.snapshot())).toEqual(expect.arrayContaining([
    expect.objectContaining({ role: 'assistant', content: '統計顯著不代表效果重要。', answerBlocks: expect.arrayContaining([expect.objectContaining({ type: 'paragraph' }), expect.objectContaining({ provider: 'generated_image' })]) }),
  ]));
  expect((await (await request.get('/__test/state')).json()).generated).toBe(1);
  await expect.poll(() => page.evaluate(async () => (window as any).imageTest.conversations())).toEqual(expect.arrayContaining([expect.objectContaining({ title: '效果量教學' })]));
  await page.reload();
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect(page.getByAltText('效果量教學圖')).toBeVisible();
  await expect(page.getByRole('status', { name: '圖片產生中' })).toHaveCount(0);
});

test('switching conversations during generation cancels work and keeps the new chat empty', async ({ page, request }) => {
  await scenario(request, 'cancel');
  await page.goto('/');
  await send(page, '請製作教學圖');
  await expect(page.getByRole('status', { name: '圖片產生中' })).toBeVisible();
  await page.getByRole('button', { name: '新增測試對話' }).click();
  await expect.poll(async () => (await (await request.get('/__test/state')).json()).cancelled).toBe(1);
  await expect(page.getByAltText('效果量教學圖')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as any).imageTest.displayMessages())).toEqual([]);
});

test('stopping generation rejects late output and cancels backend work', async ({ page, request }) => {
  await scenario(request, 'cancel');
  await page.goto('/');
  await send(page, '請製作教學圖');
  await expect(page.getByRole('status', { name: '圖片產生中' })).toBeVisible();
  await page.getByLabel('停止生成', { exact: true }).click();
  await expect(page.getByRole('status', { name: '圖片產生中' })).toHaveCount(0);
  await expect.poll(async () => (await (await request.get('/__test/state')).json()).cancelled).toBe(1);
  await expect(page.getByAltText('效果量教學圖')).toHaveCount(0);
});

test('provider failure preserves completed analysis and ends loading', async ({ page, request }) => {
  await scenario(request, 'mixed_failure');
  await page.goto('/');
  await send(page, '請先分析，再產圖');
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect(page.getByRole('status', { name: '圖片產生中' })).toHaveCount(0);
  await expect(page.getByLabel('發送訊息', { exact: true })).toBeVisible();
  expect((await (await request.get('/__test/state')).json()).generated).toBe(1);
  await scenario(request, 'image_only');
  await page.getByRole('button', { name: '重新生成訊息' }).click();
  await expect(page.getByRole('status', { name: '圖片產生中' })).toBeVisible();
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect(page.getByAltText('效果量教學圖')).toBeVisible();
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('統計顯著不代表效果重要。', { exact: true })).toBeVisible();
  await expect(page.getByAltText('效果量教學圖')).toBeVisible();
});

test('explicit Create Image uses the shared handler and preserves image proportions', async ({ page, request }) => {
  await scenario(request, 'image_only');
  await page.goto('/');
  await expect(page.getByLabel('訊息輸入框')).toBeEnabled();
  await page.getByLabel('新增', { exact: true }).click();
  await page.getByText('Create Image', { exact: true }).click();
  await send(page, '請製作繁體中文教學圖');
  const image = page.getByAltText('效果量教學圖');
  await expect(image).toBeVisible();
  await expect.poll(async () => {
    const bounds = await image.boundingBox();
    return bounds ? bounds.width / bounds.height : 0;
  }).toBeCloseTo(2, 1);
  await expect(page.getByText('Here is the image I created.', { exact: true })).toHaveCount(0);
  await expect(page.getByText('AI 生成', { exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(async () => (window as any).imageTest.conversations())).toEqual(expect.arrayContaining([expect.objectContaining({ title: '效果量教學' })]));
  expect((await (await request.get('/__test/state')).json()).generated).toBe(1);
  await image.click();
  await expect(page.getByRole('link', { name: '下載圖片' })).toBeVisible();
  await page.getByRole('button', { name: '關閉圖片檢視' }).last().click();
  await expect(page.getByRole('dialog', { name: '效果量教學圖' })).toHaveCount(0);
});

test('stopping explicit Create Image also cancels shared backend work', async ({ page, request }) => {
  await scenario(request, 'cancel');
  await page.goto('/');
  await expect(page.getByLabel('訊息輸入框')).toBeEnabled();
  await page.getByLabel('新增', { exact: true }).click();
  await page.getByText('Create Image', { exact: true }).click();
  await send(page, '請製作繁體中文教學圖');
  await expect.poll(async () => (await (await request.get('/__test/state')).json()).generated).toBe(1);
  await page.getByLabel('停止生成', { exact: true }).click();
  await expect.poll(async () => (await (await request.get('/__test/state')).json()).cancelled).toBe(1);
  await expect(page.getByRole('status', { name: '圖片產生中' })).toHaveCount(0);
  await expect(page.getByAltText('效果量教學圖')).toHaveCount(0);
});
