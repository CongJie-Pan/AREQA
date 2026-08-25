import { randomBytes } from 'crypto';
import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHARE_DEBUG_COMPONENT = 'share-conversation-route';

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

type ShareMessagePayload = NonNullable<ShareConversationPayload['messages']>[number];

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

function buildFullMessageRow(message: ShareMessagePayload, conversationId: string, userId: string) {
  return {
    id: message.id,
    user_id: userId,
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
  };
}

function buildMinimalMessageRow(message: ShareMessagePayload, conversationId: string, userId: string) {
  return {
    id: message.id,
    user_id: userId,
    conversation_id: conversationId,
    role: message.role,
    content: message.content,
    created_at: safeIsoDate(message.createdAt),
  };
}

/**
 * Returns whether share creation should emit extra operational logs.
 *
 * The default is enabled while diagnosing share-link failures. Operators can
 * disable it with AREQA_SHARE_LINK_DEBUG_LOGS=false or
 * ENABLE_SHARE_LINK_DEBUG_LOGS=false without changing code.
 */
function shareLinkDebugLogsEnabled(): boolean {
  const value = process.env.AREQA_SHARE_LINK_DEBUG_LOGS
    ?? process.env.ENABLE_SHARE_LINK_DEBUG_LOGS;
  if (value === undefined) return true;
  return !['0', 'false', 'no', 'off'].includes(value.toLowerCase());
}

/**
 * Extracts safe Supabase error metadata for structured logs.
 *
 * The returned fields intentionally exclude request headers, auth material,
 * share tokens, message content, and user identifiers. Existing logger
 * redaction still applies as a second boundary.
 */
function summarizeSupabaseError(error: unknown): Record<string, unknown> {
  if (!error || typeof error !== 'object') return {};
  const source = error as Record<string, unknown>;
  return {
    code: source.code,
    message: source.message,
    details: source.details,
    hint: source.hint,
    status: source.status,
  };
}

/**
 * Emits a gated share-link debug event with a stable component tag.
 *
 * The context must stay limited to safe operational metadata: request-scoped
 * debug IDs, conversation IDs, stage counters, and sanitized provider errors.
 */
function logShareDebug(event: string, context: Record<string, unknown>): void {
  if (!shareLinkDebugLogsEnabled()) return;
  logger.info(event, {
    component: SHARE_DEBUG_COMPONENT,
    ...context,
  });
}

export async function POST(request: NextRequest, context: RouteContext) {
  const shareDebugId = randomBytes(6).toString('hex');
  const { conversationId } = await context.params;
  logShareDebug('share.create.request_received', {
    shareDebugId,
    conversationId,
  });

  if (!UUID_PATTERN.test(conversationId)) {
    logger.warn('share.create_invalid_conversation_id', { shareDebugId });
    return NextResponse.json({ error: 'Invalid conversation id.' }, { status: 400 });
  }

  const authHeader = request.headers.get('authorization');
  if (!authHeader) {
    logger.warn('share.create_missing_auth', { shareDebugId, conversationId });
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }
  logShareDebug('share.create.auth_header_present', {
    shareDebugId,
    conversationId,
  });

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
    logger.warn('share.create_invalid_auth', {
      shareDebugId,
      conversationId,
      hasError: Boolean(userError),
      supabaseError: summarizeSupabaseError(userError),
    });
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }
  logShareDebug('share.create.authenticated', {
    shareDebugId,
    conversationId,
  });

  const payload = await request.json().catch(() => null) as ShareConversationPayload | null;
  logShareDebug('share.create.payload_received', {
    shareDebugId,
    conversationId,
    hasConversationPayload: Boolean(payload?.conversation),
    messageCount: Array.isArray(payload?.messages) ? payload.messages.length : 0,
  });

  if (payload?.conversation?.id === conversationId) {
    const now = new Date().toISOString();
    logShareDebug('share.create.conversation_upsert_started', {
      shareDebugId,
      conversationId,
      titleLength: typeof payload.conversation.title === 'string'
        ? payload.conversation.title.length
        : 0,
    });
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
      logger.error('share.create_conversation_upsert_failed', undefined, {
        shareDebugId,
        conversationId,
        supabaseError: summarizeSupabaseError(upsertConversationError),
      });
      return NextResponse.json({ error: 'Unable to sync conversation before sharing.' }, { status: 500 });
    }
    logShareDebug('share.create.conversation_upsert_succeeded', {
      shareDebugId,
      conversationId,
    });
  }

  const validMessages = Array.isArray(payload?.messages)
    ? payload.messages.filter((message) => (
      typeof message.id === 'string' &&
      UUID_PATTERN.test(message.id) &&
      (message.role === 'user' || message.role === 'assistant') &&
      typeof message.content === 'string'
    ))
    : [];
  logShareDebug('share.create.messages_validated', {
    shareDebugId,
    conversationId,
    messageCount: Array.isArray(payload?.messages) ? payload.messages.length : 0,
    validMessageCount: validMessages.length,
  });

  if (validMessages.length > 0) {
    logShareDebug('share.create.messages_upsert_started', {
      shareDebugId,
      conversationId,
      validMessageCount: validMessages.length,
    });
    const { error: upsertMessagesError } = await supabase
      .from('messages')
      .upsert(validMessages.map((message) => buildFullMessageRow(message, conversationId, user.id)));

    if (upsertMessagesError) {
      logger.warn('share.create_messages_upsert_full_failed', {
        shareDebugId,
        conversationId,
        messageCount: validMessages.length,
        supabaseError: summarizeSupabaseError(upsertMessagesError),
      });
      logShareDebug('share.create.messages_minimal_upsert_started', {
        shareDebugId,
        conversationId,
        validMessageCount: validMessages.length,
      });

      const { error: minimalUpsertMessagesError } = await supabase
        .from('messages')
        .upsert(validMessages.map((message) => buildMinimalMessageRow(message, conversationId, user.id)));

      if (minimalUpsertMessagesError) {
        logger.error('share.create_messages_upsert_failed', undefined, {
          shareDebugId,
          conversationId,
          messageCount: validMessages.length,
          supabaseError: summarizeSupabaseError(minimalUpsertMessagesError),
        });
        return NextResponse.json({ error: 'Unable to sync messages before sharing.' }, { status: 500 });
      }
    }
    logShareDebug('share.create.messages_upsert_succeeded', {
      shareDebugId,
      conversationId,
      validMessageCount: validMessages.length,
    });
  }

  logShareDebug('share.create.conversation_lookup_started', {
    shareDebugId,
    conversationId,
  });
  const { data: conversation, error: conversationError } = await supabase
    .from('conversations')
    .select('id,title')
    .eq('id', conversationId)
    .eq('user_id', user.id)
    .maybeSingle();

  if (conversationError) {
    logger.error('share.create_conversation_lookup_failed', undefined, {
      shareDebugId,
      conversationId,
      supabaseError: summarizeSupabaseError(conversationError),
    });
    return NextResponse.json({ error: 'Unable to verify conversation ownership.' }, { status: 500 });
  }

  if (!conversation) {
    logger.warn('share.create_conversation_not_found', { shareDebugId, conversationId });
    return NextResponse.json({ error: 'Conversation not found.' }, { status: 404 });
  }
  logShareDebug('share.create.conversation_lookup_succeeded', {
    shareDebugId,
    conversationId,
  });

  logShareDebug('share.create.existing_lookup_started', {
    shareDebugId,
    conversationId,
  });
  const { data: existingShare, error: existingError } = await supabase
    .from('conversation_shares')
    .select('share_token')
    .eq('conversation_id', conversationId)
    .eq('owner_user_id', user.id)
    .maybeSingle<ConversationShareRow>();

  if (existingError) {
    logger.error('share.create_existing_lookup_failed', undefined, {
      shareDebugId,
      conversationId,
      supabaseError: summarizeSupabaseError(existingError),
    });
    return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
  }

  if (existingShare?.share_token) {
    logShareDebug('share.create.existing_share_found', {
      shareDebugId,
      conversationId,
    });
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
      logger.error('share.create_existing_update_failed', undefined, {
        shareDebugId,
        conversationId,
        supabaseError: summarizeSupabaseError(updateError),
      });
      return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
    }

    logger.info('share.create_reused', { shareDebugId, conversationId });
    return NextResponse.json({ token: existingShare.share_token });
  }

  logShareDebug('share.create.insert_started', {
    shareDebugId,
    conversationId,
  });
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
    logger.error('share.create_insert_failed', undefined, {
      shareDebugId,
      conversationId,
      hasInsertedShare: Boolean(insertedShare),
      supabaseError: summarizeSupabaseError(insertError),
    });
    return NextResponse.json({ error: 'Unable to create share link.' }, { status: 500 });
  }

  logger.info('share.create_created', { shareDebugId, conversationId });
  return NextResponse.json({ token: insertedShare.share_token });
}
