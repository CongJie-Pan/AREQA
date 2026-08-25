import { randomBytes } from 'crypto';
import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface ConversationShareRow {
  share_token: string;
}

interface ShareConversationPayload {
  conversation?: {
    id?: unknown;
    title?: unknown;
    createdAt?: unknown;
    updatedAt?: unknown;
  };
  messages?: Array<{
    id?: unknown;
    role?: unknown;
    content?: unknown;
    citations?: unknown;
    searchResults?: unknown;
    sources?: unknown;
    answerBlocks?: unknown;
    suggestions?: unknown;
    reasoning?: unknown;
    attachments?: unknown;
    createdAt?: unknown;
  }>;
}

interface RouteContext {
  params: Promise<{ conversationId: string }>;
}

function createShareToken(): string {
  return randomBytes(18).toString('base64url');
}

function getSupabaseConfig(): { url: string; anonKey: string } | NextResponse {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    logger.error('share.create_config_missing');
    return NextResponse.json({ error: 'Share is not configured.' }, { status: 503 });
  }

  return { url, anonKey };
}

function safeIsoDate(value: unknown): string {
  const date = typeof value === 'string' || value instanceof Date
    ? new Date(value)
    : new Date();
  return Number.isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
}

function normalizeJsonArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { conversationId } = await context.params;
  if (!UUID_PATTERN.test(conversationId)) {
    logger.warn('share.create_invalid_conversation_id');
    return NextResponse.json({ error: 'Invalid conversation id.' }, { status: 400 });
  }

  const authHeader = request.headers.get('authorization');
  if (!authHeader) {
    logger.warn('share.create_missing_auth');
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }

  const config = getSupabaseConfig();
  if (config instanceof NextResponse) return config;

  const supabase = createClient(config.url, config.anonKey, {
    global: {
      headers: {
        Authorization: authHeader,
      },
    },
    auth: {
      persistSession: false,
    },
  });

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    logger.warn('share.create_invalid_auth', { hasError: Boolean(userError) });
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }

  const payload = await request.json().catch(() => null) as ShareConversationPayload | null;
  if (payload?.conversation?.id === conversationId) {
    const now = new Date().toISOString();
    const { error: upsertConversationError } = await supabase
      .from('conversations')
      .upsert({
        id: conversationId,
        user_id: user.id,
        title: typeof payload.conversation.title === 'string'
          ? payload.conversation.title.slice(0, 120)
          : 'Shared conversation',
        created_at: safeIsoDate(payload.conversation.createdAt),
        updated_at: safeIsoDate(payload.conversation.updatedAt ?? now),
      });

    if (upsertConversationError) {
      logger.error('share.create_conversation_upsert_failed', upsertConversationError, { conversationId });
      return NextResponse.json({ error: 'Unable to sync conversation before sharing.' }, { status: 500 });
    }
  }

  const validMessages = Array.isArray(payload?.messages)
    ? payload.messages.filter((message) => (
      typeof message.id === 'string' &&
      UUID_PATTERN.test(message.id) &&
      (message.role === 'user' || message.role === 'assistant') &&
      typeof message.content === 'string'
    ))
    : [];

  if (validMessages.length > 0) {
    const { error: upsertMessagesError } = await supabase
      .from('messages')
      .upsert(validMessages.map((message) => ({
        id: message.id,
        user_id: user.id,
        conversation_id: conversationId,
        role: message.role,
        content: message.content,
        attachments: normalizeJsonArray(message.attachments),
        citations: normalizeJsonArray(message.citations),
        search_results: normalizeJsonArray(message.searchResults),
        sources: normalizeJsonArray(message.sources),
        answer_blocks: normalizeJsonArray(message.answerBlocks),
        suggestions: normalizeJsonArray(message.suggestions),
        reasoning: message.reasoning && typeof message.reasoning === 'object' && !Array.isArray(message.reasoning)
          ? message.reasoning
          : null,
        created_at: safeIsoDate(message.createdAt),
      })));

    if (upsertMessagesError) {
      logger.error('share.create_messages_upsert_failed', upsertMessagesError, {
        conversationId,
        messageCount: validMessages.length,
      });
      return NextResponse.json({ error: 'Unable to sync messages before sharing.' }, { status: 500 });
    }
  }

  const { data: conversation, error: conversationError } = await supabase
    .from('conversations')
    .select('id,title')
    .eq('id', conversationId)
    .eq('user_id', user.id)
    .maybeSingle();

  if (conversationError) {
    logger.error('share.create_conversation_lookup_failed', conversationError, { conversationId });
    return NextResponse.json({ error: 'Unable to verify conversation ownership.' }, { status: 500 });
  }

  if (!conversation) {
    logger.warn('share.create_conversation_not_found', { conversationId });
    return NextResponse.json({ error: 'Conversation not found.' }, { status: 404 });
  }

  const { data: existingShare, error: existingError } = await supabase
    .from('conversation_shares')
    .select('share_token')
    .eq('conversation_id', conversationId)
    .eq('owner_user_id', user.id)
    .maybeSingle<ConversationShareRow>();

  if (existingError) {
    logger.error('share.create_existing_lookup_failed', existingError, { conversationId });
    return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
  }

  if (existingShare?.share_token) {
    const { error: updateError } = await supabase
      .from('conversation_shares')
      .update({
        is_public: true,
        revoked_at: null,
        updated_at: new Date().toISOString(),
      })
      .eq('conversation_id', conversationId)
      .eq('owner_user_id', user.id);

    if (updateError) {
      logger.error('share.create_existing_update_failed', updateError, { conversationId });
      return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
    }

    logger.info('share.create_reused', { conversationId });
    return NextResponse.json({ token: existingShare.share_token });
  }

  const token = createShareToken();
  const { data: insertedShare, error: insertError } = await supabase
    .from('conversation_shares')
    .insert({
      conversation_id: conversation.id,
      owner_user_id: user.id,
      share_token: token,
      is_public: true,
    })
    .select('share_token')
    .single<ConversationShareRow>();

  if (insertError || !insertedShare?.share_token) {
    logger.error('share.create_insert_failed', insertError ?? undefined, { conversationId });
    return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
  }

  logger.info('share.create_created', { conversationId });
  return NextResponse.json({ token: insertedShare.share_token });
}
