import { useEffect, useRef } from "react";
import renderMath from "../hooks/useMathRender";
import PenAnimator from "../lib/board/PenAnimator";
import "./LessonBoard.css";

/**
 * The teacher's board for a plan-driven lesson: whatever the teacher is
 * currently explaining (or last explained) rendered as chalk-on-board
 * instead of a chat bubble, with a small animated pen while it's still
 * "being written" and real LaTeX math once the text is final.
 *
 * This component only renders; it owns no animation state itself — the
 * pen's trail/loop lives entirely in PenAnimator, so this stays a thin
 * wrapper that tells the animator where the caret is and when to run.
 */
export default function LessonBoard({ text, isLive }) {
  const surfaceRef = useRef(null);
  const canvasRef = useRef(null);
  const caretRef = useRef(null);
  const penRef = useRef(null);

  useEffect(() => {
    if (canvasRef.current) penRef.current = new PenAnimator(canvasRef.current);
    return () => penRef.current?.stop();
  }, []);

  useEffect(() => {
    const surface = surfaceRef.current;
    const canvas = canvasRef.current;
    if (!surface || !canvas) return;
    penRef.current?.resize(surface.clientWidth, surface.clientHeight);
  }, [text]);

  useEffect(() => {
    const pen = penRef.current;
    if (!pen) return;
    if (!isLive) {
      pen.stop();
      if (surfaceRef.current) renderMath(surfaceRef.current);
      return;
    }
    const caret = caretRef.current;
    const surface = surfaceRef.current;
    if (caret && surface) {
      const r = caret.getBoundingClientRect();
      const s = surface.getBoundingClientRect();
      pen.moveTo(r.left - s.left, r.top - s.top + r.height / 2);
    }
    pen.start();
  }, [text, isLive]);

  if (!text) return null;

  return (
    <div className="lesson-board">
      <div className="lesson-board-surface" dir="rtl" ref={surfaceRef}>
        <span>{text}</span>
        <span className="board-caret" ref={caretRef} />
        <canvas className="board-pen-canvas" ref={canvasRef} />
      </div>
    </div>
  );
}
