/** Authenticated proxy for compiling request-scoped attachments into an image brief. */
import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Sign in to create an image' }, { status: 401 });
  }
  const clientId = getClientIdentifier(request);
  if (!checkRateLimit(`image-reference:${clientId}`, { maxRequests: 6, windowMs: 60_000 }).allowed) {
    return NextResponse.json({ error: 'Image reference rate limit exceeded' }, { status: 429 });
  }
  if (Number(request.headers.get('content-length')) > 22 * 1024 * 1024) {
    return NextResponse.json({ error: 'Attachments too large' }, { status: 413 });
  }
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: 'Invalid attachment request' }, { status: 400 });
  }
  const files = form.getAll('attachments');
  const prompt = form.get('prompt');
  const conversationId = form.get('conversation_id');
  if (typeof prompt !== 'string' || prompt.trim().length < 3 || prompt.length > 1800
    || typeof conversationId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(conversationId)
    || files.length === 0 || files.length > 5 || files.some((file) => typeof file === 'string')) {
    return NextResponse.json({ error: 'Invalid attachment request' }, { status: 400 });
  }
  const uploads = files as File[];
  if (uploads.some((file) => file.size > 5 * 1024 * 1024)
    || uploads.reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024) {
    return NextResponse.json({ error: 'Attachments too large' }, { status: 413 });
  }
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
    const upstream = await fetch(`${backendUrl}/api/v1/images/reference`, {
      method: 'POST', headers: { Authorization: authorization }, body: form, signal: request.signal,
    });
    if (!upstream.ok) {
      logger.warn('image_reference_proxy_failed', { status: upstream.status });
      return NextResponse.json({ error: 'Image reference preparation is unavailable' }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.warn('image_reference_proxy_network_failed', { reason: error instanceof Error ? error.name : 'UnknownError' });
    return NextResponse.json({ error: 'Image reference preparation is unavailable' }, { status: 503 });
  }
}
