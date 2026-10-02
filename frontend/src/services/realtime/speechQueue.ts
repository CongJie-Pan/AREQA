import { normalizeReadbackText } from './readbackText';

/**
 * Serialize backend sentences against generation AND playback completion.
 * Args: callbacks own transport requests, captions, and terminal recovery.
 * Side effects: starts one speech request at a time; never interrupts to advance.
 * Cancellation discards buffered text and fences all late response events.
 */
export class SpeechQueue {
  private buffer = '';
  private pending: string[] = [];
  private active: { text: string; requestId: string; responseId?: string; generated: boolean; played: boolean; started: boolean } | null = null;
  private sequence = 0;
  private ended = false;
  private closed = false;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(private readonly callbacks: {
    id: string;
    speak: (text: string, requestId: string) => boolean;
    caption: (text: string) => void;
    complete: (failed: boolean) => void;
  }) {}

  /** Buffer raw stream chunks until a sentence boundary is available. */
  append(chunk: string): void {
    if (this.closed || this.ended) return;
    this.buffer += chunk;
    // Keep decimals and abbreviations intact; incomplete trailing sentences wait.
    const segments = Array.from(new Intl.Segmenter(undefined, { granularity: 'sentence' }).segment(this.buffer));
    let consumed = 0;
    for (const segment of segments) {
      if (segment.index + segment.segment.length === this.buffer.length && !/[.!?。！？]["”’']*\s+$/u.test(segment.segment)) break;
      this.add(segment.segment);
      consumed = segment.index + segment.segment.length;
    }
    this.buffer = this.buffer.slice(consumed);
    this.pump();
  }

  /** Flush the last sentence once the upstream stream has completed. */
  finish(): void {
    if (this.closed) return;
    this.add(this.buffer);
    this.buffer = '';
    this.ended = true;
    this.pump();
  }

  private add(raw: string): void {
    const text = normalizeReadbackText(raw);
    // Bound each provider request without silently losing text at its 6000-char cap.
    let remaining = text;
    while (remaining.length > 1200) {
      const space = remaining.lastIndexOf(' ', 1200);
      const end = space > 600 ? space : 1200;
      this.pending.push(remaining.slice(0, end));
      remaining = remaining.slice(end).trimStart();
    }
    if (remaining) this.pending.push(remaining);
  }

  private pump(): void {
    if (this.closed || this.active) return;
    const text = this.pending.shift();
    if (!text) {
      if (this.ended) { this.closed = true; this.callbacks.complete(false); }
      return;
    }
    const requestId = `${this.callbacks.id}:${++this.sequence}`;
    this.active = { text, requestId, generated: false, played: false, started: false };
    // A missing provider event must not wedge the conversation or retry speech.
    this.timer = setTimeout(() => this.fail(), 90_000);
    if (!this.callbacks.speak(text, requestId)) this.fail();
  }

  /** Bind provider response identity to the request that owns this sentence. */
  responseStarted(responseId: string, requestId?: string): boolean {
    if (!this.active || requestId !== this.active.requestId) return false;
    this.active.responseId = responseId;
    return true;
  }

  /** Generation completion alone never releases the next sentence. */
  responseDone(responseId: string, status: string): void {
    if (!this.active || responseId !== this.active.responseId) return;
    if (status !== 'completed') { this.fail(); return; }
    this.active.generated = true;
    this.advance();
  }

  /** Reveal only the currently playing sentence; ignore old response events. */
  playback(state: 'started' | 'stopped' | 'interrupted', responseId?: string): void {
    if (!this.active || !responseId || responseId !== this.active.responseId) return;
    if (state === 'interrupted') { this.fail(); return; }
    if (state === 'started' && !this.active.started) {
      this.active.started = true;
      this.callbacks.caption(this.active.text);
    }
    if (state === 'stopped') this.active.played = true;
    this.advance();
  }

  private advance(): void {
    if (!this.active?.generated || !this.active.played) return;
    clearTimeout(this.timer);
    this.active = null;
    this.pump();
  }

  private fail(): void {
    if (this.closed) return;
    this.cancel();
    this.callbacks.complete(true);
  }

  /** Drop queued speech without replaying or changing already displayed text. */
  cancel(): void {
    this.closed = true;
    this.buffer = '';
    this.pending = [];
    this.active = null;
    clearTimeout(this.timer);
  }
}
