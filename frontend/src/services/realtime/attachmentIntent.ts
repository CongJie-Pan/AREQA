/** Conversation-local intents used to resume a voice task after file upload. */
export type VoiceAttachmentTask = 'read' | 'summarize' | 'explain' | 'wait';

/**
 * Recognize a file task without treating upload chatter as a new request.
 *
 * Args:
 *   transcript: Finalized learner speech or text; never written to logs.
 *   hasAttachmentContext: Whether a file or a pending file task supplies the referent.
 * Returns:
 *   The requested task, including an explicit pause, or null for unrelated speech.
 */
export function getVoiceAttachmentTask(transcript: string, hasAttachmentContext = false): VoiceAttachmentTask | null {
  let text = transcript.trim();
  const mentionsFile = /(檔案|档案|附件|文件|資料|资料|論文|论文|逐字稿|file|attachment|document|paper|transcript|material|pdf)/i.test(text);
  if (!mentionsFile && !hasAttachmentContext) return null;
  if (/(先不要|暫時不要|暂时不要|先別|先别).{0,12}(讀|读|說|说|回覆|回复|解釋|解释|解說|解说|摘要|整理)|^(不用了|取消|算了)[。！!\s]*$|\b(wait|cancel|never mind)\b|\b(do not|don't)\b.{0,12}\b(speak|respond|answer|reply)\b/i.test(text)) return 'wait';
  // A rejected action may be followed by a replacement task, e.g. "don't
  // read it aloud; summarize it". Only affirmative actions should be resumed.
  const affirmativeText = text.replace(/(?:不要|不用|別|别)\s*(?:逐字|直接)?\s*(?:朗讀|朗读|閱讀|阅读|讀|读|解釋|解释|解說|解说|摘要|整理)|\b(?:do not|don't)\s+(?:read|explain|summari[sz]e)\b/gi, '');
  const rejectedAction = affirmativeText !== text;
  text = affirmativeText;
  if (/(摘要|重點|重点|summary|summari[sz]e|總結|总结|整理)/i.test(text)) return 'summarize';
  if (/(解說|解说|解釋|解释|分析|explain|analy[sz]e)/i.test(text)) return 'explain';
  if (/(閱讀|阅读|讀|读|朗讀|朗读|\bread\b)/i.test(text)) return 'read';
  if (mentionsFile && /(看一下|看看|看.{0,6}(資料|资料|檔案|文件)|\b(look|review)\b)/i.test(text)) return 'explain';
  return rejectedAction ? 'wait' : null;
}

/**
 * Build a fresh-upload task that produces content in the same voice reply.
 *
 * Args:
 *   task: Earlier file task; absent intents default to a short explanation.
 *   request: Bounded learner wording, preserving requested language and scope.
 * Returns:
 *   Speakable task instructions; the caller handles explicit pauses separately.
 */
export function buildVoiceAttachmentRequest(task: VoiceAttachmentTask | null, request = ''): string {
  const action = task === 'read'
    ? 'Read aloud from the available file text now.'
    : task === 'summarize'
      ? 'Give a source-grounded summary with the key ideas now.'
      : 'Explain the central idea and the main points of the available file text now.';
  return [
    'The newly uploaded attachment is ready in this voice conversation. Briefly acknowledge receipt, then complete the requested task in this same reply.',
    request.trim() ? `Learner request: ${request.trim().slice(0, 2000)}` : '',
    action,
    'Provide substantive content immediately; do not end with a promise to read or summarize later, and do not ask the learner to repeat the request.',
    'If only an excerpt is available, state that briefly and use it without claiming to have read the entire file.',
  ].filter(Boolean).join('\n\n');
}
