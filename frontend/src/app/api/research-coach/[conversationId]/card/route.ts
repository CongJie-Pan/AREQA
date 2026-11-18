/** Authenticated proxy: read a Topic Finder topic card. */
import { NextRequest } from 'next/server';
import { proxyTopicCard } from '../../proxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest, context: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await context.params;
  return proxyTopicCard(request, conversationId, 'card');
}
