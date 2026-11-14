import { useEffect, useRef } from "react";
import renderMath from "../hooks/useMathRender";
import PenAnimator from "../lib/board/PenAnimator";
import "./LessonBoard.css";

const PEN_FLOURISH_MS = 900;

/**
 * The teacher's board for a plan-driven lesson — NOT a mirror of the chat:
 * only the short key-point notes the teacher explicitly "writes" land here
 * (see backend's teacher.split_board_notes), never the full spoken
 * explanation. Content is organized into pages; once a page fills up a new
 * one starts, and the caller can flip between them.
 *
 * Rendering-only: pages/pageIndex are owned by the caller (ChatPanel, via
 * BoardPaginator). This component just shows the current page, runs a
 * short pen flourish whenever it changes, and renders KaTeX once the text
 * is settled — safe here because a page's text is always already final
 * (board notes arrive as one complete chunk, never streamed token-by-token).
 */
export default function LessonBoard({ pages, pageIndex, onPrev, onNext }) {
  const surfaceRef = useRef(null);
  const canvasRef = useRef(null);
  const caretRef = useRef(null);
  const penRef = useRef(null);

  useEffect(() => {
    if (canvasRef.current) penRef.current = new PenAnimator(canvasRef.current);
    return () => penRef.current?.stop();
  }, []);

  const pageText = pages[pageIndex] || "";

  useEffect(() => {
    const surface = surfaceRef.current;
    const canvas = canvasRef.current;
    const pen = penRef.current;
    if (!surface || !canvas || !pen || !pageText) return;

    pen.resize(surface.clientWidth, surface.clientHeight);
    renderMath(surface);

    const caret = caretRef.current;
    if (caret) {
      const r = caret.getBoundingClientRect();
      const s = surface.getBoundingClientRect();
      pen.moveTo(r.left - s.left, r.top - s.top + r.height / 2);
    }
    pen.start();
    const timer = setTimeout(() => pen.stop(), PEN_FLOURISH_MS);
    return () => clearTimeout(timer);
  }, [pageText]);

  if (!pageText) return null;

  return (
    <div className="lesson-board">
      <div className="lesson-board-surface" dir="rtl" ref={surfaceRef}>
        <span>{pageText}</span>
        <span className="board-caret" ref={caretRef} />
        <canvas className="board-pen-canvas" ref={canvasRef} />
      </div>
      {pages.length > 1 && (
        <div className="board-pager">
          <button className="board-pager-btn" onClick={onPrev} disabled={pageIndex === 0}>‹ דף קודם</button>
          <span className="board-page-indicator">דף {pageIndex + 1}/{pages.length}</span>
          <button className="board-pager-btn" onClick={onNext} disabled={pageIndex === pages.length - 1}>דף הבא ›</button>
        </div>
      )}
    </div>
  );
}
