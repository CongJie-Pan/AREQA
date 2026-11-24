/** Authenticated proxy: the learner declines the AI draft for the version they saw. */
import { NextRequest } from 'next/server';
import { proxyTopicCard } from '../../proxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest, context: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await context.params;
  return proxyTopicCard(request, conversationId, 'reject');
}
