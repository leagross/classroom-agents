import { useEffect, useRef } from "react";
import renderMath from "../../hooks/useMathRender";
import "./LessonBoard.css";

/**
 * The classroom board: one surface, the way a real classroom has one front
 * wall. The teacher writes on it, and — for a lesson whose type calls for
 * it — a presentation is projected on it too. Both are there at once; the
 * teacher keeps writing while a slide is up. They are not two views to
 * switch between.
 *
 * Whether there is a projection at all is a property of the lesson (its
 * plan says so), passed in as `presentation`. A lesson without one is just
 * the writing board, full size.
 *
 * Presentational only — what is written, and which page/slide is showing,
 * is owned by useLessonBoard and useLessonSlides.
 */
export default function LessonBoard({
  pages,
  pageIndex,
  writing,
  onPrev,
  onNext,
  onSkipAnimation,
  focused,
  onToggleFocus,
  statusLabel,
  presentation = false,
  slides,
}) {
  const surfaceRef = useRef(null);
  const projectionRef = useRef(null);
  const entries = pages[pageIndex] || [];

  // The projection area exists while the deck is on its way (so the layout
  // doesn't jump when it arrives) and once it has arrived. If the deck
  // failed to build, it is dropped and the writing board takes the whole
  // surface: a design problem must never cost the lesson its board.
  const showProjection = presentation && !slides?.failed && (slides?.loading || slides?.hasSlides);
  const slide = slides?.slide || null;

  // Formulas are LaTeX, so they have to be typeset — but only once nothing
  // is mid-animation. A half-written formula is unbalanced ("$f'(x) = \lim_{h")
  // and typesetting it would render garbage and replace the text nodes the
  // animation is still driving.
  const isAnimating = Boolean(writing);
  useEffect(() => {
    if (!isAnimating && surfaceRef.current) renderMath(surfaceRef.current);
  }, [entries, isAnimating, pageIndex]);
  useEffect(() => {
    if (projectionRef.current) renderMath(projectionRef.current);
  }, [slide]);

  return (
    <section
      className={"board" + (focused ? " focused" : "") + (showProjection ? " with-projection" : "")}
      aria-label="לוח הכיתה"
    >
      <header className="board-top">
        <span className="board-title">הלוח</span>
        {statusLabel && <span className="board-status">{statusLabel}</span>}
        <div className="board-top-actions">
          <button
            className="board-focus-btn"
            onClick={onToggleFocus}
            title={focused ? "החזר את הלוח לצד" : "הגדל את הלוח למרכז"}
          >
            {focused ? "⤡ לצד" : "⤢ למרכז"}
          </button>
        </div>
      </header>

      <div className="board-body">
        {showProjection && (
          <div className="board-projection">
            <div className="projection-screen" ref={projectionRef}>
              {slides.loading && !slide ? (
                <p className="projection-loading">המורה מכין מצגת…</p>
              ) : slide?.image_url ? (
                // image_url exists only once a design provider is wired up
                // (backend/slides.py); until then the text is the slide.
                <img src={slide.image_url} alt={slide.title || "שקופית"} />
              ) : (
                <div className="projection-text">
                  {slide?.title && <h3>{slide.title}</h3>}
                  {(slide?.bullets || []).map((bullet, i) => (
                    <p key={i}>{bullet}</p>
                  ))}
                </div>
              )}
            </div>
            {slides.count > 0 && (
              <div className="projection-pager">
                <button onClick={slides.prev} disabled={slides.slideIndex === 0} title="שקופית קודמת">‹</button>
                <span>
                  שקופית {slides.slideIndex + 1} מתוך {slides.count}
                </span>
                <button
                  onClick={slides.next}
                  disabled={slides.slideIndex >= slides.count - 1}
                  title="שקופית הבאה"
                >
                  ›
                </button>
              </div>
            )}
          </div>
        )}

        <div className="board-writing">
          <div className="board-surface" ref={surfaceRef} onClick={onSkipAnimation}>
            {entries.length === 0 && !writing ? (
              <p className="board-empty">הלוח עדיין ריק — המורה יכתוב כאן את הנקודות המרכזיות.</p>
            ) : (
              <div className="board-lines">
                {entries.map((entry) => {
                  const isWriting = writing && writing.id === entry.id;
                  const text = isWriting ? writing.revealed : entry.text;
                  return (
                    <div key={entry.id} className={"board-entry " + entry.kind + (isWriting ? " writing" : "")}>
                      {text}
                      {isWriting && <span className="chalk-cursor" aria-hidden="true" />}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <footer className="board-pager">
            <button onClick={onPrev} disabled={pageIndex === 0} title="דף קודם">‹</button>
            <span>
              דף {pageIndex + 1} מתוך {pages.length}
            </span>
            <button onClick={onNext} disabled={pageIndex >= pages.length - 1} title="דף הבא">
              ›
            </button>
          </footer>
        </div>
      </div>
    </section>
  );
}
