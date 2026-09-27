import { describe, expect, it } from 'vitest';
import { shouldCreateImageForVoiceTurn } from '@/services/realtime/imageIntent';

describe('voice image intent', () => {
  it('accepts direct visual requests and structured explanations', () => {
    expect(shouldCreateImageForVoiceTurn('幫我畫一張血液循環圖')).toBe(true);
    expect(shouldCreateImageForVoiceTurn('Explain the structure of a cell')).toBe(true);
  });

  it('does not create paid images for ordinary voice turns', () => {
    expect(shouldCreateImageForVoiceTurn('你好')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('What is photosynthesis?')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('我的學習計畫是每天讀書')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('不要生成圖片，口頭說明即可')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('Do not draw an image')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('請解釋水循環，但不要畫圖')).toBe(false);
    expect(shouldCreateImageForVoiceTurn('不要畫圖，請畫一張細胞圖')).toBe(true);
  });
});
