import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Supabase client acting as the signed-in caller.
 *
 * Collaborative routes never use a service key: membership is decided by the
 * security definer functions with the caller's own JWT, so these routes only
 * shape requests and responses.
 */
export function createCallerClient(request: NextRequest): SupabaseClient | NextResponse {
  const authHeader = request.headers.get('authorization');
  if (!authHeader) {
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    logger.error('collab.config_missing');
    return NextResponse.json({ error: 'Collaboration is not configured.' }, { status: 503 });
  }
  return createClient(url, anonKey, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });
}

/** Map database errors raised by the collaboration functions to HTTP status codes. */
export function statusForRpcError(error: { code?: string; message?: string }): number {
  if (error.code === '42501') return 403;
  if (error.code === 'P0002') return 404;
  if (error.code === '22023') return 400;
  if (error.code === 'PGRST202') return 503;
  if (error.code === 'PGRST301' || error.message?.includes('JWT')) return 401;
  return 500;
}
