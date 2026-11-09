import { defineConfig } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import { resolve } from 'node:path';

export default defineConfig({
  testDir: __dirname, testMatch: 'flow.spec.ts', workers: 1,
  timeout: 30_000, expect: { timeout: 5000 },
  outputDir: '/tmp/areqa-sidebar-toggle-playwright',
  use: { baseURL: 'http://127.0.0.1:18106', headless: true, trace: 'retain-on-failure' },
  webServer: {
    command: 'node frontend/node_modules/vite/bin/vite.js --config tests/e2e/sidebar-toggle/vite.config.ts',
    cwd: resolve(__dirname, '../../..'), url: 'http://127.0.0.1:18106', timeout: 60_000,
  },
});
