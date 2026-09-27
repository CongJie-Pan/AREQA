/** Conservative voice trigger for educational image creation. */

const EXPLICIT_IMAGE_REQUEST = /((?:請|幫我|帮我|可以|能|要|想|給我|给我)?(?:畫|画)(?:一|出|個|个|張|张|圖|图)|產圖|生成圖片|生成图|示意圖|示意图|圖解|图解|\bdraw\b|\bsketch\b|illustrat|make (?:an? |the )?image|create (?:an? |the )?image|visuali[sz]e)/i;
const EXPLANATION_REQUEST = /(解釋|解释|講解|讲解|說明|说明|explain|show me how)/i;
const VISUAL_STRUCTURE = /(流程|結構|结构|循環|循环|路徑|路径|解剖|電路|电路|空間|空间|process|structure|cycle|anatomy|circuit|spatial)/i;

/** Return true only for explicit drawing or visually grounded explanations. */
export function shouldCreateImageForVoiceTurn(transcript: string): boolean {
  const text = transcript.trim();
  if (text.length < 3) return false;
  return EXPLICIT_IMAGE_REQUEST.test(text)
    || (EXPLANATION_REQUEST.test(text) && VISUAL_STRUCTURE.test(text));
}
