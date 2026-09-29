import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import React from 'react';
import { createRequire } from 'node:module';
import type * as TS from 'typescript';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

  it('does not insert routing status as a sibling of the message list', () => {
    const source = readFileSync(filename, 'utf8');
    expect(source).not.toContain('Understanding your request');
    expect(source).not.toContain('isRoutingMessage && <p');
  });

  it.each(['', '請解釋這張圖', '請分析附件', '幫我產圖', '隨便一句包含圖的文字'])('sends every untagged request through the same chat pipeline: %s', async (content) => {
    const { scope, send } = setup();
    const file = new File(['source'], 'source.png', { type: 'image/png' });
    expect(await send(content, [file])).toEqual({ completed: true });
    expect(scope.sendMessage).toHaveBeenCalledWith(content, 'conv-a', [file]);
    expect(scope.resolveMessageRoute).not.toHaveBeenCalled();
    expect(authenticatedFetch).not.toHaveBeenCalled();
    expect(scope.generateConversationImage).not.toHaveBeenCalled();
  });

  it('delivers typed chat to the independently owned voice session', async () => {
    const { scope, send } = setup();
    const voiceSend = vi.fn().mockResolvedValue({ completed: true });
    scope.useLiveTutorStore.getState = () => ({ isOpen: true, sendVoiceMessage: voiceSend });
    expect(await send('你好')).toEqual({ completed: true });
    expect(voiceSend).toHaveBeenCalledWith('你好', []);
    expect(scope.resolveMessageRoute).not.toHaveBeenCalled();
  });

  it('keeps the explicit image tag on its existing image lifecycle', async () => {
    const { scope, send } = setup();
    await send('畫一隻貓', [], { createImage: true });
    expect(scope.resolveMessageRoute).not.toHaveBeenCalled();
    expect(scope.generateConversationImage).toHaveBeenCalledWith('畫一隻貓', 'conv-a', 'zh-TW', true, { attachments: [] });
    expect(scope.sendMessage).not.toHaveBeenCalled();
  });
});
