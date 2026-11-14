import { defineConfig } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import { resolve } from 'node:path';

const executablePath = process.env.AREQA_TEST_CHROMIUM;
export default defineConfig({
  testDir: __dirname,
  testMatch: 'flow.spec.ts',
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  outputDir: '/tmp/areqa-conversation-branches-playwright',
  use: {
    baseURL: 'http://127.0.0.1:18108',
    headless: true,
    trace: 'retain-on-failure',
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  webServer: {
    command: 'node frontend/node_modules/vite/bin/vite.js --config tests/e2e/conversation-branches/vite.config.ts',
    cwd: resolve(__dirname, '../../..'),
    url: 'http://127.0.0.1:18108',
    timeout: 60_000,
  },
});
