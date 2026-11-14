/**
 * Owns the lesson board's content as a sequence of pages: a new note is
 * appended to the current page unless that would push it over a size
 * threshold, in which case a fresh page starts — mirroring how a physical
 * whiteboard fills up and you flip to a clean one, instead of cramming
 * everything onto a single surface.
 *
 * Knows nothing about React or how notes arrive (SSE, tests, whatever) —
 * it only tracks pages of text and hands back a fresh array each time, so
 * a React caller can just setState(paginator.append(...)) directly.
 */
export default class BoardPaginator {
  constructor({ maxPageChars = 420 } = {}) {
    this.maxPageChars = maxPageChars;
    this.pages = [""];
  }

  /** Appends a short note chunk (already short — the teacher writes key points, not full speech). */
  append(text) {
    const current = this.pages[this.pages.length - 1];
    const merged = current ? `${current}\n\n${text}` : text;
    this.pages = merged.length > this.maxPageChars && current
      ? [...this.pages, text]
      : [...this.pages.slice(0, -1), merged];
    return this.pages;
  }

  reset() {
    this.pages = [""];
    return this.pages;
  }
}
