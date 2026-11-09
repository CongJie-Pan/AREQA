import { defineConfig } from '../../../frontend/node_modules/vite/dist/node/index.js';
import tailwindcss from '../../../frontend/node_modules/@tailwindcss/postcss/dist/index.mjs';
import { resolve } from 'node:path';

export default defineConfig({
  root: __dirname,
  publicDir: resolve(__dirname, '../../../frontend/public'),
  resolve: { alias: [
    { find: '@', replacement: resolve(__dirname, '../../../frontend/src') },
    { find: 'react', replacement: resolve(__dirname, '../../../frontend/node_modules/react') },
    { find: 'react-dom', replacement: resolve(__dirname, '../../../frontend/node_modules/react-dom') },
    { find: 'antd', replacement: resolve(__dirname, '../../../frontend/node_modules/antd') },
  ] },
  css: { postcss: { plugins: [tailwindcss()] } },
  define: { 'process.env': JSON.stringify({ NODE_ENV: 'development' }) },
  esbuild: { jsx: 'automatic' },
  server: { host: '127.0.0.1', port: 18106, strictPort: true, fs: { allow: [resolve(__dirname, '../../..')] } },
});
