import { defineConfig } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import { resolve } from 'node:path';

const baseURL = process.env.AREQA_TEST_BASE_URL || 'http://127.0.0.1:3005';

export default defineConfig({
  testDir: __dirname,
  testMatch: '*.spec.ts',
  workers: 2,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: '/tmp/areqa-initial-render-playwright',
  use: { baseURL, headless: true, trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  webServer: process.env.AREQA_TEST_BASE_URL ? undefined : {
    command: 'npm --prefix frontend run dev -- --port 3005',
    cwd: resolve(__dirname, '../../..'),
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
