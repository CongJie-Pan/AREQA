import { describe, expect, it } from 'vitest';
import { buildVoiceAttachmentRequest, getVoiceAttachmentTask } from '@/services/realtime/attachmentIntent';

describe('spoken attachment tasks', () => {
  it.each([
    ['對的，我有一份資料給你看，可以看一下嗎？', 'explain'],
    ['請閱讀這份檔案', 'read'],
    ['你讀這份檔案，然後給我一些summary', 'summarize'],
    ['Please summarize the attached file', 'summarize'],
    ['請解釋這份文件', 'explain'],
    ['先不要解說這份附件', 'wait'],
    ['不要逐字讀這份檔案，請幫我摘要', 'summarize'],
    ["Don't read the file aloud; summarize it", 'summarize'],
  ] as const)('recognizes the task in %s', (transcript, task) => {
    expect(getVoiceAttachmentTask(transcript)).toBe(task);
  });

  it('preserves the task across upload chatter and acknowledgements', () => {
    expect(getVoiceAttachmentTask('我先上傳檔案')).toBeNull();
    expect(getVoiceAttachmentTask('嗯，好。', true)).toBeNull();
    expect(getVoiceAttachmentTask('請解釋量子電腦')).toBeNull();
    expect(getVoiceAttachmentTask('給我一些summary')).toBeNull();
    expect(getVoiceAttachmentTask('給我一些summary', true)).toBe('summarize');
    expect(getVoiceAttachmentTask('不用了', true)).toBe('wait');
  });

  it('requires content now and limits claims to available text', () => {
    const request = buildVoiceAttachmentRequest('summarize', '請用中文摘要');
    expect(request).toContain('請用中文摘要');
    expect(request).toContain('source-grounded summary');
    expect(request).toContain('in this same reply');
    expect(request).toContain('without claiming to have read the entire file');
  });
});
