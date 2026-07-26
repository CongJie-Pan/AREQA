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
        src: '/icon/logo_icon_v2.png',
        sizes: '382x382',
        type: 'image/png',
        purpose: 'maskable',
      },
      {
        src: '/icon/areqa_icon_v3.png',
        sizes: '238x224',
        type: 'image/png',
        purpose: 'any',
      },
    ],
  };
}
