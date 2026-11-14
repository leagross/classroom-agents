/**
 * Draws a small moving "pen tip" with a fading ink trail on a canvas,
 * following wherever the board's caller says the writing caret currently
 * is. Purely a visual flourish so the teacher's board feels handwritten
 * instead of text just appearing — it owns nothing about *what* is written
 * (that stays plain DOM text + KaTeX, so math still renders correctly);
 * it only owns the canvas and its own animation-frame loop.
 */
export default class PenAnimator {
  constructor(canvas, { trailLength = 24, trailFadeMs = 500 } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.trailLength = trailLength;
    this.trailFadeMs = trailFadeMs;
    this.frameId = null;
    this.targetX = 0;
    this.targetY = 0;
    this.trail = [];
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
  }

  /** Called whenever the caret (end of revealed text) moves to a new spot. */
  moveTo(x, y) {
    this.targetX = x;
    this.targetY = y;
    this.trail.push({ x, y, t: performance.now() });
    if (this.trail.length > this.trailLength) this.trail.shift();
  }

  start() {
    if (this.frameId) return;
    const loop = () => {
      this._draw();
      this.frameId = requestAnimationFrame(loop);
    };
    this.frameId = requestAnimationFrame(loop);
  }

  stop() {
    if (this.frameId) cancelAnimationFrame(this.frameId);
    this.frameId = null;
    this._clear();
  }

  _clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  _draw() {
    this._clear();
    const now = performance.now();

    this.ctx.lineCap = "round";
    for (let i = 1; i < this.trail.length; i++) {
      const prev = this.trail[i - 1];
      const curr = this.trail[i];
      const alpha = Math.max(0, 1 - (now - curr.t) / this.trailFadeMs);
      if (alpha <= 0) continue;
      this.ctx.strokeStyle = `rgba(241, 245, 249, ${alpha * 0.6})`;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(prev.x, prev.y);
      this.ctx.lineTo(curr.x, curr.y);
      this.ctx.stroke();
    }

    this.ctx.fillStyle = "#f8fafc";
    this.ctx.beginPath();
    this.ctx.arc(this.targetX, this.targetY, 3, 0, Math.PI * 2);
    this.ctx.fill();
  }
}
