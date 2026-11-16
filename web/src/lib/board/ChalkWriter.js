/**
 * The handwriting feel: reveals text progressively, as if being written.
 *
 * Driven by elapsed time rather than a per-frame character count, so the
 * writing speed is the same on a 60Hz and a 144Hz screen, and a tab that
 * was backgrounded catches up instead of falling behind.
 *
 * Deliberately knows nothing about the DOM or React — it reports progress
 * through onUpdate and the component renders whatever prefix it is handed.
 * That also makes it trivial to stop: there is no element to clean up.
 */

const DEFAULT_CHARS_PER_SECOND = 42;

export default class ChalkWriter {
  constructor({ charsPerSecond = DEFAULT_CHARS_PER_SECOND, onUpdate, onDone } = {}) {
    this.charsPerSecond = charsPerSecond;
    this.onUpdate = onUpdate || (() => {});
    this.onDone = onDone || (() => {});
    this._frame = null;
    this._text = "";
    this._startedAt = 0;
  }

  get isWriting() {
    return this._frame !== null;
  }

  /** Begin writing `text`. Replaces anything currently being written. */
  write(text) {
    this.stop();
    this._text = String(text || "");
    if (!this._text) {
      this.onDone();
      return;
    }
    this._startedAt = performance.now();
    this._tick();
  }

  _tick = () => {
    const elapsedSeconds = (performance.now() - this._startedAt) / 1000;
    const revealed = Math.floor(elapsedSeconds * this.charsPerSecond);
    if (revealed >= this._text.length) {
      this._frame = null;
      this.onUpdate(this._text);
      this.onDone();
      return;
    }
    this.onUpdate(this._text.slice(0, revealed));
    this._frame = requestAnimationFrame(this._tick);
  };

  /** Finish immediately — used when the student navigates away from the
   *  page being written, or clicks to skip the animation. */
  skip() {
    if (!this.isWriting) return;
    this.stop();
    this.onUpdate(this._text);
    this.onDone();
  }

  stop() {
    if (this._frame !== null) {
      cancelAnimationFrame(this._frame);
      this._frame = null;
    }
  }
}
