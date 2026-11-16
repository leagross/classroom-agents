import { useEffect, useRef } from "react";
import renderMath from "../../hooks/useMathRender";
import "./LessonBoard.css";

/**
 * The classroom board. Presentational only — what is written on it, and
 * which page is showing, is owned by useLessonBoard.
 *
 * Two things it shows: the written notes (default), and a presentation
 * slide when one is supplied. The "focus" control doesn't live here — the
 * classroom layout owns whether the board is the side panel or the centre
 * of the screen (see Classroom.css), because that decision affects the chat
 * just as much as the board.
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
  // Slides are optional: a lesson is perfectly usable without them.
  view = "notes", // "notes" | "slides"
  onChangeView,
  slides,
}) {
  const surfaceRef = useRef(null);
  const entries = pages[pageIndex] || [];
  const showingSlides = view === "slides" && slides?.hasSlides;
  const slide = showingSlides ? slides.slide : null;

  // Formulas are written in LaTeX, so they have to be typeset — but only
  // once nothing is mid-animation. A half-written formula is unbalanced
  // LaTeX ("$f'(x) = \lim_{h"), and typesetting that would both render
  // garbage and replace the text nodes React is still animating.
  const isAnimating = Boolean(writing);
  useEffect(() => {
    if (!isAnimating && surfaceRef.current) renderMath(surfaceRef.current);
  }, [entries, isAnimating, pageIndex, slide]);

  const pageCount = pages.length;

  return (
    <section className={"board" + (focused ? " focused" : "")} aria-label="לוח הכיתה">
      <header className="board-top">
        <span className="board-title">הלוח</span>
        {statusLabel && <span className="board-status">{statusLabel}</span>}
        <div className="board-top-actions">
          {slides?.hasSlides && (
            <div className="board-view-switch" role="group" aria-label="תצוגת הלוח">
              <button
                className={view === "notes" ? "active" : ""}
                onClick={() => onChangeView?.("notes")}
              >
                כתב יד
              </button>
              <button
                className={view === "slides" ? "active" : ""}
                onClick={() => onChangeView?.("slides")}
              >
                מצגת
              </button>
            </div>
          )}
          <button
            className="board-focus-btn"
            onClick={onToggleFocus}
            title={focused ? "החזר את הלוח לצד" : "הגדל את הלוח למרכז"}
          >
            {focused ? "⤡ לצד" : "⤢ למרכז"}
          </button>
        </div>
      </header>

      <div className="board-surface" ref={surfaceRef} onClick={onSkipAnimation}>
        {slide ? (
          <div className="board-slide">
            {/* image_url appears only once a design provider is wired up
                (see backend/slides.py); until then the text is the slide. */}
            {slide.image_url ? (
              <img src={slide.image_url} alt={slide.title || "שקופית"} />
            ) : (
              <div className="board-slide-text">
                {slide.title && <h3>{slide.title}</h3>}
                {(slide.bullets || []).map((bullet, i) => (
                  <p key={i}>{bullet}</p>
                ))}
              </div>
            )}
          </div>
        ) : entries.length === 0 && !writing ? (
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
        {showingSlides ? (
          <>
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
          </>
        ) : (
          <>
            <button onClick={onPrev} disabled={pageIndex === 0} title="דף קודם">‹</button>
            <span>
              דף {pageIndex + 1} מתוך {pageCount}
            </span>
            <button onClick={onNext} disabled={pageIndex >= pageCount - 1} title="דף הבא">
              ›
            </button>
          </>
        )}
      </footer>
    </section>
  );
}
