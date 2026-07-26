import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'AREQA',
    short_name: 'AREQA',
    description: 'Adaptive RAG-based Educational QA System',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#130f18',
    theme_color: '#d8a25c',
    icons: [
      {
        src: '/icon/areqa_app_icon_192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icon/areqa_app_icon_192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'maskable',
      },
      {
        src: '/icon/areqa_app_icon_512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icon/areqa_app_icon_512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
