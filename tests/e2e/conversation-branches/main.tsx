import React from 'react';
import { createRoot } from 'react-dom/client';
import { AppProviders } from '@/app/providers';
import { ChatContainer } from '@/components/ChatContainer';
import { useAuthStore } from '@/store/auth';
import { useFeatureStore } from '@/store/features';
import '@/app/globals.css';

const user = { id: 'branch-smoke-user', app_metadata: {}, user_metadata: {}, aud: 'authenticated', created_at: '' };
localStorage.setItem('areqa:interface-language', 'zh-TW');
localStorage.setItem('sb-branch-smoke-auth-token', JSON.stringify({
  user,
  access_token: 'test-only',
  expires_at: 4102444800,
}));

useAuthStore.setState({
  user,
  isInitialized: true,
  initialize: async () => {},
  validateSession: async () => true,
});
useFeatureStore.setState({ initialized: true, fetchFeatures: async () => {} });
createRoot(document.getElementById('root')!).render(<AppProviders><ChatContainer /></AppProviders>);
