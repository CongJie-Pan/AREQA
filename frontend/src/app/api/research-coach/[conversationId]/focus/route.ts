/** Authenticated proxy: the learner sets the coach's current focus gap aside. */
import { NextRequest } from 'next/server';
import { proxyTopicCard } from '../../proxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest, context: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await context.params;
  return proxyTopicCard(request, conversationId, 'focus');
}
