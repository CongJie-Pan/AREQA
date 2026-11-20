/**
 * Home Page
 * Main entry point for the AREQA chat application.
 */

import { ChatContainer } from '@/components/ChatContainer';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;

interface HomeProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function Home({ searchParams }: HomeProps) {
  const { share } = await searchParams;
  // Known on the server so the first paint of `/?share=` is already the quiet
  // loading state, not a new chat that is replaced a moment later.
  const openingShare = typeof share === 'string' && SHARE_TOKEN_PATTERN.test(share);
  return <ChatContainer openingShare={openingShare} />;
}
