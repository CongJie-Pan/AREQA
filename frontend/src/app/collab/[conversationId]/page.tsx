import { notFound } from 'next/navigation';
import { CollaborativeConversationView } from './CollaborativeConversationView';

export const dynamic = 'force-dynamic';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface CollabPageProps {
  params: Promise<{ conversationId: string }>;
}

export default async function CollabPage({ params }: CollabPageProps) {
  const { conversationId } = await params;
  if (!UUID_PATTERN.test(conversationId)) notFound();
  return <CollaborativeConversationView conversationId={conversationId} />;
}
