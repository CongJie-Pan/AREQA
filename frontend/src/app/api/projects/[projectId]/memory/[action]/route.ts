/**
 * Authenticated proxy for project memory: `refresh` rebuilds the profile from the
 * project's conversations, `revise` applies the learner's correction.
 *
 * The bearer token is forwarded so FastAPI reads the project through RLS. Logs
 * carry only the action and status, never the instruction or memory text.
 */
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACTIONS = new Set(['refresh', 'revise']);
const MAX_INSTRUCTION_CHARS = 1000;

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ projectId: string; action: string }> },
) {
  const { projectId, action } = await context.params;
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) return NextResponse.json({ error: 'Sign in required' }, { status: 401 });
  if (!UUID_PATTERN.test(projectId) || !ACTIONS.has(action)) {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }

  let body: string | undefined;
  if (action === 'revise') {
    if (Number(request.headers.get('content-length')) > 8_000) {
      return NextResponse.json({ error: 'Request too large' }, { status: 413 });
    }
    try {
      const payload = (await request.json()) as { instruction?: unknown } | null;
      const instruction = typeof payload?.instruction === 'string' ? payload.instruction.trim() : '';
      if (!instruction || instruction.length > MAX_INSTRUCTION_CHARS) throw new Error('Invalid instruction');
      body = JSON.stringify({ instruction });
    } catch {
      return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
    }
  }

  try {
    const upstream = await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000'}/api/v1/projects/${projectId}/memory/${action}`,
      {
        method: 'POST',
        headers: { Authorization: authorization, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body,
        cache: 'no-store',
        signal: request.signal,
      },
    );
    if (!upstream.ok) {
      logger.info('project_memory_proxy_upstream_error', { action, status: upstream.status });
      return NextResponse.json({ error: 'Project memory unavailable' }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.warn('project_memory_proxy_failed', { action, reason: error instanceof Error ? error.name : 'UnknownError' });
    return NextResponse.json({ error: 'Project memory unavailable' }, { status: 503 });
  }
}
