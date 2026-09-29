import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import React from 'react';
import { createRequire } from 'node:module';
import type * as TS from 'typescript';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveMessageRoute } from '@/services/messageIntent';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useChatStore } from '@/store/chat';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/database/db', () => ({ getCurrentUserId: () => 'user-a' }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn() } }));

const ts = createRequire(resolve(process.cwd(), 'package.json'))('typescript') as typeof TS;

// Execute the actual send boundary without mounting unrelated auth/history effects.
const filename = resolve(process.cwd(), 'src/components/ChatContainer/index.tsx');
const ast = ts.createSourceFile(filename, readFileSync(filename, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handlerSource = '';
function findHandler(node: TS.Node): void {
  if (ts.isFunctionExpression(node) && node.name?.text === 'retryableSend') handlerSource = node.getText(ast);
  ts.forEachChild(node, findHandler);
}
findHandler(ast);
if (!handlerSource) throw new Error('ChatContainer send boundary unavailable');
const script = ts.transpileModule(`const handler = ${handlerSource}; handler;`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
}).outputText;

function setup() {
  const routingController: { current: AbortController | null } = { current: null };
  const scope = {
    React, AbortController, user: { id: 'user-a' }, activeConversationId: 'conv-a', language: 'zh-TW', routingController,
    setIsRoutingMessage: vi.fn(), setShowAuthPrompt: vi.fn(),
    resolveMessageRoute: vi.fn().mockResolvedValue({ createImage: true, attachments: [] }),
    generateConversationImage: vi.fn().mockResolvedValue({ completed: true }),
    sendMessage: vi.fn().mockResolvedValue({ completed: true }),
    useLiveTutorStore: { getState: () => ({ isOpen: false }) },
    supabase: { auth: { getSession: async () => ({ data: { session: {} } }) } },
    logger: { warn: vi.fn() }, getErrorMessage: () => ({ message: 'Routing unavailable', isRetryable: false }),
    antMessageApi: { error: vi.fn(), destroy: vi.fn(), success: vi.fn() }, t: (value: string) => value,
  };
  const send = runInNewContext(script, scope) as (content: string, files?: File[], options?: { createImage?: boolean }) => Promise<{ completed: boolean; cancelled?: boolean }>;
  return { scope, send };
}

describe('ChatContainer executable send boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({ messages: [] });
  });

  it('sends ordinary text through the actual fallback resolver when classification returns 503', async () => {
    const { scope, send } = setup();
    const file = new File(['notes'], 'notes.txt', { type: 'text/plain' });
    scope.resolveMessageRoute.mockImplementation(resolveMessageRoute);
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status: 503 }));
    expect(await send('你好，請解釋效果量', [file])).toEqual({ completed: true });
    expect(scope.sendMessage).toHaveBeenCalledWith('你好，請解釋效果量', 'conv-a', [file]);
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
    expect(scope.antMessageApi.error).not.toHaveBeenCalled();
  });

  it('keeps image requests explicit when the actual classifier is unavailable', async () => {
    const { scope, send } = setup();
    scope.resolveMessageRoute.mockImplementation(resolveMessageRoute);
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status: 503 }));
    await expect(send('幫我產圖')).rejects.toThrow('503');
    expect(scope.sendMessage).not.toHaveBeenCalled();
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
  });
  it('dispatches an untagged upload generation decision to the existing image lifecycle', async () => {
    const { scope, send } = setup();
    const file = new File(['png'], 'source.png', { type: 'image/png' });
    scope.resolveMessageRoute.mockResolvedValue({ createImage: true, attachments: [file] });
    await send('幫我產圖', [file]);
    expect(scope.generateConversationImage).toHaveBeenCalledWith('幫我產圖', 'conv-a', 'zh-TW', true, { attachments: [file], referenceBrief: undefined });
    expect(scope.sendMessage).not.toHaveBeenCalled();
  });

  it('keeps text decisions and attachments in the normal chat pipeline', async () => {
    const { scope, send } = setup();
    const file = new File(['png'], 'source.png', { type: 'image/png' });
    scope.resolveMessageRoute.mockResolvedValue({ createImage: false, attachments: [file] });
    await send('請解釋這張圖', [file]);
    expect(scope.sendMessage).toHaveBeenCalledWith('請解釋這張圖', 'conv-a', [file]);
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
  });

  it('bypasses semantic classification for an explicit image tag', async () => {
    const { scope, send } = setup();
    await send('畫一隻貓', [], { createImage: true });
    expect(scope.resolveMessageRoute).not.toHaveBeenCalled();
    expect(scope.generateConversationImage).toHaveBeenCalledOnce();
  });

  it('does not execute a late image decision after cancellation', async () => {
    const { scope, send } = setup();
    scope.resolveMessageRoute.mockImplementation(async () => {
      scope.routingController.current?.abort();
      return { createImage: true, attachments: [] };
    });
    expect(await send('畫一隻貓')).toEqual({ completed: false, cancelled: true });
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
    expect(scope.sendMessage).not.toHaveBeenCalled();
    expect(scope.routingController.current).toBeNull();
  });

  it('surfaces classifier failure and never silently falls back to text', async () => {
    const { scope, send } = setup();
    scope.resolveMessageRoute.mockRejectedValue(new Error('Routing unavailable'));
    await expect(send('幫我產圖')).rejects.toThrow('Routing unavailable');
    expect(scope.sendMessage).not.toHaveBeenCalled();
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
    expect(scope.antMessageApi.error).toHaveBeenCalledOnce();
  });
});
