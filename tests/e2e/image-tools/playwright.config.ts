import { defineConfig } from '../../../frontend/node_modules/@playwright/test/index.mjs';
import { resolve } from 'node:path';

export default defineConfig({
  testDir: __dirname, testMatch: 'flow.spec.ts', workers: 1,
  timeout: 60_000, expect: { timeout: 15_000 },
  outputDir: '/tmp/areqa-image-tools-playwright',
  use: { baseURL: 'http://127.0.0.1:18101', headless: true, trace: 'retain-on-failure' },
  webServer: [
    { command: 'PYTHONPATH=backend:src/main/python backend/.venv/bin/python -m uvicorn e2e_app:app --app-dir tests/e2e/image-tools --host 127.0.0.1 --port 18100', cwd: resolve(__dirname, '../../..'), url: 'http://127.0.0.1:18100/__test/state', timeout: 120_000 },
    { command: 'node frontend/node_modules/vite/bin/vite.js --config tests/e2e/image-tools/vite.config.ts', cwd: resolve(__dirname, '../../..'), url: 'http://127.0.0.1:18101', timeout: 120_000 },
  ],
});
