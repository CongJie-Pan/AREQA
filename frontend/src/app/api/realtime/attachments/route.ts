import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);
  if (!checkRateLimit(clientId, { maxRequests: 20, windowMs: 60_000 }).allowed) {
    return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });
  }
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
  try {
    const form = await request.formData();
    const upstream = await fetch(`${backendUrl}/api/v1/realtime/attachments`, {
      method: 'POST',
      headers: request.headers.get('authorization')
        ? { Authorization: request.headers.get('authorization') as string }
        : {},
      body: form,
      signal: request.signal,
    });
    return NextResponse.json(await upstream.json(), { status: upstream.status });
  } catch (error) {
    logger.warn('Realtime attachment preparation failed', {
      clientId,
      errorName: error instanceof Error ? error.name : 'UnknownError',
    });
    return NextResponse.json({ error: 'Attachment preparation unavailable' }, { status: 503 });
  }
}
