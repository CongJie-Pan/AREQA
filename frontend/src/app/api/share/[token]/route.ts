import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;

interface RouteContext {
  params: Promise<{ token: string }>;
}

function getSupabaseConfig(): { url: string; anonKey: string } | NextResponse {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    logger.error('share.read_config_missing');
    return NextResponse.json({ error: 'Share is not configured.' }, { status: 503 });
  }

  return { url, anonKey };
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const { token } = await context.params;
  if (!SHARE_TOKEN_PATTERN.test(token)) {
    logger.warn('share.read_invalid_token', { tokenLength: token.length });
    return NextResponse.json({ error: 'Invalid share link.' }, { status: 400 });
  }

  const config = getSupabaseConfig();
  if (config instanceof NextResponse) return config;

  const supabase = createClient(config.url, config.anonKey, {
    auth: {
      persistSession: false,
    },
  });

  const { data, error } = await supabase.rpc('get_public_conversation_share', {
    p_share_token: token,
  });

  if (error) {
    logger.error('share.read_rpc_failed', error, { tokenLength: token.length });
    return NextResponse.json({ error: 'Unable to load shared conversation.' }, { status: 500 });
  }

  if (!data) {
    logger.info('share.read_not_found', { tokenLength: token.length });
    return NextResponse.json({ error: 'Shared conversation not found.' }, { status: 404 });
  }

  logger.info('share.read_loaded', { tokenLength: token.length });
  return NextResponse.json(data);
}
