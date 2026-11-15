import { describe, expect, it } from 'vitest';
import { readRequestModesFromClipboard, requestModesClipboardHtml } from '@/utils/requestModeClipboard';

const labels = { create_image: 'Create Image', english_tutor: 'English Tutor' } as const;
const clipboard = (data: Record<string, string>) => ({ getData: (type: string) => data[type] ?? '' });

describe('request mode clipboard', () => {
  it('round-trips the copy button payload', () => {
    const html = requestModesClipboardHtml(['create_image'], labels, '請幫我將此畫成圖解釋\n第二行');
    expect(readRequestModesFromClipboard(clipboard({ 'text/html': html, 'text/plain': '請幫我將此畫成圖解釋\n第二行' })))
      .toEqual({ modes: ['create_image'], text: '請幫我將此畫成圖解釋\n第二行' });
  });

  it('reads a manual selection of the bubble and strips the token labels from the text', () => {
    const html = '<div><span data-areqa-mode="english_tutor">English Tutor</span><span data-areqa-mode="create_image">Create Image</span> <p>Check my essay</p></div>';
    expect(readRequestModesFromClipboard(clipboard({ 'text/html': html, 'text/plain': 'English Tutor Create Image Check my essay' })))
      .toEqual({ modes: ['english_tutor', 'create_image'], text: 'Check my essay' });
  });

  it('leaves ordinary pastes alone', () => {
    expect(readRequestModesFromClipboard(clipboard({ 'text/html': '<p>hello</p>', 'text/plain': 'hello' }))).toBeNull();
    expect(readRequestModesFromClipboard(clipboard({ 'text/plain': 'hello' }))).toBeNull();
    expect(readRequestModesFromClipboard(null)).toBeNull();
  });

  it('ignores unknown mode markers', () => {
    const html = '<span data-areqa-mode="delete_everything">x</span> hi';
    expect(readRequestModesFromClipboard(clipboard({ 'text/html': html, 'text/plain': 'x hi' }))).toBeNull();
  });

  it('escapes the question text in the HTML payload', () => {
    expect(requestModesClipboardHtml(['create_image'], labels, '<img src=x onerror=alert(1)>')).not.toContain('<img');
  });
});
