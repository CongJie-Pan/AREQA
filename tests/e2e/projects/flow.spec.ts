import { expect, test, type Page } from '../../../frontend/node_modules/@playwright/test/index.mjs';

/**
 * Projects smoke: the real ChatContainer in a browser, with Supabase's
 * `projects` table, the chat stream, titles and project memory faked at the
 * network edge. IndexedDB and every store run for real, so reloads are real.
 */

type Row = Record<string, unknown> & { id: string };

async function mockBackend(page: Page) {
  const streamRequests: Array<Record<string, unknown>> = [];
  const projects = new Map<string, Row>();
  const memoryCalls: string[] = [];
  await page.addLocatorHandler(page.getByRole('button', { name: '略過引導' }), async (button) => { await button.click(); });
  await page.route('**/api/chat', async (route) => {
    streamRequests.push(route.request().postDataJSON());
    await route.fulfill({
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ choices: [{ delta: { content: `回覆第${streamRequests.length}輪` } }] })}\n\ndata: [DONE]\n\n`,
    });
  });
  await page.route('**/api/title', (route) => route.fulfill({
    contentType: 'text/event-stream', body: 'data: {"content":"專案對話"}\n\ndata: [DONE]\n\n',
  }));
  // Supabase PostgREST for the projects table (upsert = POST, list = GET, delete = DELETE).
  await page.route('**/rest/v1/projects**', async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      const body = request.postDataJSON();
      for (const row of Array.isArray(body) ? body : [body]) projects.set(row.id, row);
      return route.fulfill({ status: 201, body: '' });
    }
    if (request.method() === 'DELETE') {
      const id = new URL(request.url()).searchParams.get('id')?.replace('eq.', '');
      if (id) projects.delete(id);
      return route.fulfill({ status: 204, body: '' });
    }
    return route.fulfill({ json: [...projects.values()] });
  });
  await page.route('**/api/projects/*/memory/*', async (route) => {
    const [, projectId, , action] = new URL(route.request().url()).pathname.split('/').slice(2);
    memoryCalls.push(`${projectId}:${action}`);
    const memory = { summary: '碩一學生，每晚寫日記', details: ['住在台北宿舍'], updated_at: new Date().toISOString() };
    const current = projects.get(projectId);
    if (current) projects.set(projectId, { ...current, memory_summary: memory.summary, memory_details: memory.details,
      memory_updated_at: memory.updated_at, updated_at: memory.updated_at });
    return route.fulfill({ json: { memory, refreshed: true } });
  });
  return { streamRequests, projects, memoryCalls };
}

async function send(page: Page, content: string) {
  // The composer remounts while history loads after navigation; retype until the text sticks.
  await expect(async () => {
    await page.getByLabel('訊息輸入框').fill(content);
    await expect(page.getByRole('button', { name: '發送訊息', exact: true })).toBeEnabled({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
  await page.getByRole('button', { name: '發送訊息', exact: true }).click();
}

async function createProject(page: Page, name: string) {
  await page.getByRole('button', { name: '建立專案', exact: true }).click();
  await page.getByLabel('專案名稱').fill(name);
  await page.getByRole('dialog').getByRole('button', { name: /儲\s*存/ }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
}

test('@smoke creating a project opens its page and survives a reload', async ({ page }) => {
  const { projects } = await mockBackend(page);
  await page.goto('/');

  await createProject(page, 'Diary');
  await expect(page.getByPlaceholder('在 Diary 中新增工作階段')).toBeVisible();
  await expect.poll(() => [...projects.values()].map((row) => row.name)).toEqual(['Diary']);

  await page.reload();
  await page.getByRole('button', { name: '專案', exact: true }).click();
  await expect(page.getByRole('heading', { name: '專案', exact: true })).toBeVisible();
  await expect(page.getByText('Diary', { exact: true })).toBeVisible();
});

test('@smoke the first message on a project page starts a project chat that sends project_id', async ({ page }) => {
  const { streamRequests, projects } = await mockBackend(page);
  await page.goto('/');
  await createProject(page, 'Diary');
  const projectId = [...projects.keys()][0];

  await send(page, '今天好累');

  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();
  expect(streamRequests[0]).toMatchObject({ project_id: projectId });
  await send(page, '再多說一點');
  await expect(page.getByText('回覆第2輪', { exact: true })).toBeVisible();
  expect(streamRequests[1]).toMatchObject({ project_id: projectId });

  // A plain new chat is outside the project.
  await page.getByRole('button', { name: '新對話', exact: true }).first().click();
  await send(page, '一般問題');
  await expect(page.getByText('回覆第3輪', { exact: true })).toBeVisible();
  expect(streamRequests[2]).not.toHaveProperty('project_id');

  // The project page lists only its own chat.
  await page.getByRole('button', { name: '專案', exact: true }).click();
  await page.getByText('Diary', { exact: true }).click();
  // Both chats share the mocked title; only the project chat is listed in the main column.
  await expect(page.locator('.areqa-chat-main').getByText('專案對話', { exact: true })).toHaveCount(1);
});

test('@smoke instructions, memory and the account-memory switch reach the project row', async ({ page }) => {
  const { projects, memoryCalls } = await mockBackend(page);
  await page.goto('/');
  await createProject(page, 'Diary');
  const projectId = [...projects.keys()][0];
  const side = page.locator('aside').filter({ hasText: '記憶' });

  await side.getByRole('button', { name: '新增', exact: true }).click();
  await page.getByRole('dialog', { name: '指示' }).getByRole('textbox').fill('先給重點');
  await page.getByRole('dialog', { name: '指示' }).getByRole('button', { name: /儲\s*存/ }).click();
  await expect.poll(() => projects.get(projectId)?.instructions).toBe('先給重點');
  await expect(side.getByText('先給重點')).toBeVisible();

  await side.getByRole('button', { name: '檢視', exact: true }).click();
  const memory = page.getByRole('dialog', { name: '記憶' });
  await memory.getByRole('button', { name: /^更\s*新$/ }).click();
  await expect(memory.getByText('碩一學生，每晚寫日記')).toBeVisible();
  expect(memoryCalls).toContain(`${projectId}:refresh`);

  await memory.getByRole('switch', { name: '使用帳號記憶' }).click();
  await expect.poll(() => projects.get(projectId)?.use_account_memory).toBe(false);
});

test('@smoke an existing chat can be added to a project from the sidebar menu', async ({ page }) => {
  const { streamRequests, projects } = await mockBackend(page);
  await page.goto('/');
  await send(page, '一般問題');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();
  expect(streamRequests[0]).not.toHaveProperty('project_id');

  await createProject(page, 'Research');
  const projectId = [...projects.keys()][0];
  await page.locator('[data-conversation-id]').first().getByTitle('對話選單').click();
  await page.getByRole('menuitem', { name: /加入專案/ }).hover();
  await page.getByRole('menuitem', { name: 'Research', exact: true }).click();
  await expect(page.getByText('已加入「Research」')).toBeVisible();

  await page.locator('[data-conversation-id]').first().click();
  await send(page, '接著問');
  await expect(page.getByText('回覆第2輪', { exact: true })).toBeVisible();
  expect(streamRequests[1]).toMatchObject({ project_id: projectId });
});

test('@smoke the layout follows the reference screens (images 01–07)', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await createProject(page, 'Diary');
  await send(page, '今天好累');
  await expect(page.getByText('回覆第1輪', { exact: true })).toBeVisible();

  // 01: list page with a two-column card grid; pinning shows a filled pin.
  await page.getByRole('button', { name: '專案', exact: true }).click();
  const card = page.locator('[role=button]').filter({ hasText: 'Diary' }).first();
  await card.hover();
  await card.getByRole('button', { name: '釘選', exact: true }).click();
  await expect(card.getByRole('button', { name: '取消釘選', exact: true })).toBeVisible();

  // 02: the pinned project sits in the Pinned group with its chat nested under it.
  const nested = page.locator('[data-project-conversation-id]');
  await expect(nested).toHaveCount(1);
  await expect(nested).toHaveClass(/areqa-conversation-project-child/);
  await expect(page.getByTitle('專案選單')).toHaveCount(1);

  // 03: project page top bar, serif title, session placeholder, side rows and "私人".
  await card.click();
  await expect(page.getByRole('navigation', { name: '專案' })).toContainText('Diary');
  await expect(page.getByPlaceholder('在 Diary 中新增工作階段')).toBeVisible();
  const side = page.locator('aside').filter({ hasText: '記憶' });
  await expect(side).toContainText('指示');
  await expect(side).toContainText('私人');
  await expect(side).not.toContainText('排程');
  await expect(side).not.toContainText('背景資訊');

  // 04–06: memory row reveals Edit on hover; detail shows bullets and the pill input.
  await side.getByRole('button', { name: '檢視', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '記憶' });
  await expect(dialog.getByText('碩一學生，每晚寫日記')).toBeVisible();
  await expect(dialog.getByRole('button', { name: /^更\s*新$/ })).toHaveCount(0);
  await dialog.getByRole('group', { name: '概況' }).hover();
  await dialog.getByRole('button', { name: '編輯', exact: true }).click();
  await expect(page.getByRole('dialog').locator('li')).toHaveText(['住在台北宿舍']);
  await expect(page.getByRole('dialog').getByPlaceholder('告訴 AREQA 要修改什麼')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click();

  // 07: the chat menu order and the Add to project flyout with its search field.
  const row = page.locator('[data-conversation-id]').first();
  await row.hover();
  await row.getByTitle('對話選單').click();
  const labels = await page.locator('.ant-dropdown:visible .ant-dropdown-menu-root > .ant-dropdown-menu-item, .ant-dropdown:visible .ant-dropdown-menu-root > .ant-dropdown-menu-submenu').allTextContents();
  expect(labels.slice(0, 3)).toEqual(['釘選聊天', '重新命名', '加入專案']);
  await page.getByRole('menuitem', { name: /加入專案/ }).hover();
  await expect(page.getByLabel('搜尋或建立專案')).toBeVisible();
  await expect(page.getByRole('menuitem', { name: /新增專案/ })).toBeVisible();
});
