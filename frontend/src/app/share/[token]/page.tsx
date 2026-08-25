import { createClient } from '@supabase/supabase-js';
import { notFound } from 'next/navigation';
import {
  SharedConversationView,
  type SharedConversation,
} from './SharedConversationView';

export const dynamic = 'force-dynamic';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;

interface SharePageProps {
  params: Promise<{ token: string }>;
}

function createPublicSupabaseClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) return null;

  return createClient(url, anonKey, {
    auth: {
      persistSession: false,
    },
  });
}

async function getSharedConversation(token: string): Promise<SharedConversation | null> {
  if (!SHARE_TOKEN_PATTERN.test(token)) return null;

  const supabase = createPublicSupabaseClient();
  if (!supabase) return null;

  const { data, error } = await supabase.rpc('get_public_conversation_share', {
    p_share_token: token,
  });

  if (error || !data) return null;
  return data as SharedConversation;
}

export default async function SharePage({ params }: SharePageProps) {
  const { token } = await params;
  const conversation = await getSharedConversation(token);

  if (!conversation) notFound();

  return <SharedConversationView conversation={conversation} />;
}
