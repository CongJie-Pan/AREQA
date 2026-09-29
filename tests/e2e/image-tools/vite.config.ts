import { defineConfig } from '../../../frontend/node_modules/vite/dist/node/index.js';
import { resolve } from 'node:path';

export default defineConfig({
  root: __dirname,
  resolve: { alias: [
    { find: '@/services/syncService', replacement: resolve(__dirname, 'sync.ts') },
    { find: '@', replacement: resolve(__dirname, '../../../frontend/src') },
    { find: 'react', replacement: resolve(__dirname, '../../../frontend/node_modules/react') },
    { find: 'react-dom', replacement: resolve(__dirname, '../../../frontend/node_modules/react-dom') },
  ] },
  define: { 'process.env': JSON.stringify({ NODE_ENV: 'development' }) },
  esbuild: { jsx: 'automatic' },
  server: {
    host: '127.0.0.1', port: 18101, strictPort: true,
    fs: { allow: [resolve(__dirname, '../../..')] },
    proxy: {
      '/api/chat': { target: 'http://127.0.0.1:18100', rewrite: () => '/api/v1/stream' },
      '/api/images': {
        target: 'http://127.0.0.1:18100',
        rewrite: (path) => path.replace('/api/images', '/api/v1/images'),
        configure(proxy) {
          // Match the production BFF's request.signal propagation for JSON requests.
          proxy.on('proxyReq', (upstream, _request, response) => {
            response.on('close', () => {
              if (!response.writableEnded) upstream.destroy();
            });
          });
        },
      },
      '/api/title': { target: 'http://127.0.0.1:18100' },
      '/__test': { target: 'http://127.0.0.1:18100' },
    },
  },
});
