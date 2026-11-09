import React from 'react';
import { createRoot } from 'react-dom/client';
import { ChatContainer } from '@/components/ChatContainer';
import { AppProviders } from '@/app/providers';
import { useAuthStore } from '@/store/auth';
import { useFeatureStore } from '@/store/features';
import '@/app/globals.css';

// Keep the full UI and CSS real while isolating remote account/feature lookups.
useAuthStore.setState({ user: null, isInitialized: true, initialize: async () => {}, validateSession: async () => false });
useFeatureStore.setState({ initialized: true, fetchFeatures: async () => {} });
createRoot(document.getElementById('root')!).render(<AppProviders><ChatContainer /></AppProviders>);
