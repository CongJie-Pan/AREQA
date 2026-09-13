/**
 * Voice-turn routing helpers for AREQA Live Tutor deep answers.
 *
 * The live voice model remains responsible for immediate conversational
 * turn-taking. These helpers identify turns that should also run through the
 * established AREQA text orchestration pipeline so document and learning
 * questions can receive grounded, full-depth answers in the chat surface.
 */

const DOCUMENT_TERMS = [
  'paper',
  'pdf',
  'article',
  'study',
  'methodology',
  'method',
  'experiment',
  'baseline',
  '論文',
  '文章',
  '文件',
  '研究',
  '方法',
  '實驗',
  '摘要',
  '結論',
  '限制',
  '贡献',
  '貢獻',
];

const EXPLANATION_TERMS = [
  'explain',
  'analyze',
  'compare',
  'critique',
  'walkthrough',
  'derive',
  'why',
  'how',
  'detail',
  'deep',
  'example',
  '請解釋',
  '解釋',
  '分析',
  '比較',
  '為什麼',
  '为什么',
  '如何',
  '怎麼',
  '怎么',
  '深入',
  '詳細',
  '细节',
  '例子',
  '舉例',
  '推導',
  '批判',
];

const QUICK_TURN_PATTERN = /^(hi|hello|hey|ok|okay|thanks|thank you|謝謝|谢谢|好|可以|你好|嗨)[。！？!,.，\s]*$/i;

/**
 * Decide whether a finalized voice transcript should invoke backend depth.
 *
 * Args:
 *   transcript: Final user speech transcript after language normalization.
 *
 * Returns:
 *   True when the turn appears to need AREQA's grounded text pipeline rather
 *   than only a short live-voice answer.
 *
 * Compatibility:
 *   This is intentionally conservative for greetings and acknowledgements. A
 *   false negative still receives the live model answer; a true positive runs
 *   the existing chat stream and can be interrupted by the same voice controls.
 */
export function shouldDelegateVoiceTurnToDeepAnswer(transcript: string): boolean {
  const normalized = transcript.trim().toLowerCase();
  if (!normalized || QUICK_TURN_PATTERN.test(normalized)) return false;

  const hasDocumentTerm = DOCUMENT_TERMS.some((term) => normalized.includes(term.toLowerCase()));
  const hasExplanationTerm = EXPLANATION_TERMS.some((term) => normalized.includes(term.toLowerCase()));
  if (hasDocumentTerm && hasExplanationTerm) return true;

  return [
    'deep dive',
    'go deep',
    '研究生',
    'meeting',
    '完整說明',
    '完整解释',
    '詳細說明',
    '深入說明',
    '幫我整理',
    '帮我整理',
  ].some((term) => normalized.includes(term.toLowerCase()));
}
