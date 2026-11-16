/**
 * What is written on the lesson board, as a model of a physical board.
 *
 * A real board fills up by LINES, not by character count — a teacher writes
 * a heading, a formula, a key sentence, and when the surface runs out they
 * start a fresh page rather than writing smaller. So capacity here is
 * measured in lines (including the lines a long entry wraps onto), and a
 * new page opens when the next entry would not fit on the current one.
 *
 * Entries are kept as discrete blocks rather than one concatenated string,
 * so the view can animate the newest one being written while the earlier
 * ones just sit there, and so an entry can carry its own kind (heading /
 * formula / note) for styling.
 *
 * No DOM, no React, no timers — all of that lives in ChalkWriter and the
 * LessonBoard component. This file is pure state and is directly testable.
 */

export const DEFAULT_MAX_LINES = 13;
export const DEFAULT_CHARS_PER_LINE = 38;

/** Formulas are delimited for KaTeX ($...$ / $$...$$); a line that is
 *  mostly delimited math is treated as a formula entry, and a short line
 *  ending in ':' reads as a heading, exactly as on a real board. */
function classify(text) {
  const trimmed = text.trim();
  if (/^\$\$?[\s\S]*\$\$?$/.test(trimmed)) return "formula";
  if (trimmed.length <= 32 && trimmed.endsWith(":")) return "heading";
  return "note";
}

function countLines(text, charsPerLine) {
  return text
    .split("\n")
    .reduce((total, line) => total + Math.max(1, Math.ceil(line.trim().length / charsPerLine)), 0);
}

export default class BoardModel {
  constructor({ maxLines = DEFAULT_MAX_LINES, charsPerLine = DEFAULT_CHARS_PER_LINE } = {}) {
    this.maxLines = maxLines;
    this.charsPerLine = charsPerLine;
    this.pages = [[]];
    this._nextId = 1;
  }

  get pageCount() {
    return this.pages.length;
  }

  get lastPageIndex() {
    return this.pages.length - 1;
  }

  page(index) {
    return this.pages[index] || [];
  }

  linesOn(index) {
    return this.page(index).reduce((total, entry) => total + entry.lines, 0);
  }

  /**
   * Write one block of notes on the board.
   *
   * Splits the incoming text into its own lines first, so a 4-line block
   * becomes 4 styled entries (a heading and three notes, say) instead of
   * one undifferentiated paragraph — which is what makes it read like
   * handwriting rather than a chat message pasted onto a board.
   *
   * Returns { pageIndex, entries, openedNewPage } describing what changed.
   */
  write(text) {
    const blocks = String(text || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (!blocks.length) return { pageIndex: this.lastPageIndex, entries: [], openedNewPage: false };

    const needed = blocks.reduce((total, block) => total + countLines(block, this.charsPerLine), 0);
    let pageIndex = this.lastPageIndex;
    let openedNewPage = false;

    // Only move to a fresh page if something is already written here —
    // an entry taller than a whole empty page still has to go somewhere.
    if (this.linesOn(pageIndex) > 0 && this.linesOn(pageIndex) + needed > this.maxLines) {
      this.pages.push([]);
      pageIndex = this.lastPageIndex;
      openedNewPage = true;
    }

    const entries = blocks.map((block) => ({
      id: this._nextId++,
      text: block,
      kind: classify(block),
      lines: countLines(block, this.charsPerLine),
    }));
    this.pages[pageIndex].push(...entries);
    return { pageIndex, entries, openedNewPage };
  }

  reset() {
    this.pages = [[]];
    this._nextId = 1;
  }

  isEmpty() {
    return this.pages.every((page) => page.length === 0);
  }

  /** Plain text of one page, for the lesson-summary export. */
  textOf(index) {
    return this.page(index)
      .map((entry) => entry.text)
      .join("\n");
  }

  /** Every page's text, in order — what the export needs. */
  allPagesText() {
    return this.pages.map((_, index) => this.textOf(index));
  }
}
