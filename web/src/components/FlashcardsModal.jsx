import { useEffect, useRef, useState } from "react";
import { fetchFlashcards } from "../lib/api/chat";
import renderMath from "../hooks/useMathRender";
import "./FlashcardsModal.css";

export default function FlashcardsModal({ open, sessionId, onClose, onCardsLoaded }) {
  const [cards, setCards] = useState(null);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [error, setError] = useState("");
  const cardRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setCards(null);
    setIndex(0);
    setFlipped(false);
    setError("");
    fetchFlashcards(sessionId)
      .then((cs) => {
        setCards(cs);
        onCardsLoaded?.(cs);
      })
      .catch((e) => setError(e.message));
  }, [open, sessionId]);

  useEffect(() => {
    if (cards && cardRef.current) renderMath(cardRef.current);
  }, [cards, index, flipped]);

  if (!open) return null;

  const card = cards?.[index];

  function next() {
    setFlipped(false);
    setIndex((i) => Math.min((cards?.length || 1) - 1, i + 1));
  }

  function prev() {
    setFlipped(false);
    setIndex((i) => Math.max(0, i - 1));
  }

  return (
    <div className="modal-overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal flashcards-modal">
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>כרטיסיות לחזרה</h3>

        {error && <p className="setup-error">{error}</p>}
        {!error && !cards && <p>בונה כרטיסיות על השיעור...</p>}

        {card && (
          <>
            <div className="flashcard" ref={cardRef} onClick={() => setFlipped((f) => !f)}>
              {flipped ? card.back : card.front}
            </div>
            <p className="flashcard-hint">לחץ על הכרטיסייה כדי להפוך</p>
            <div className="flashcard-nav">
              <button className="btn btn-ghost" onClick={prev} disabled={index === 0}>‹ קודם</button>
              <span className="flashcard-count">{index + 1}/{cards.length}</span>
              <button className="btn btn-ghost" onClick={next} disabled={index === cards.length - 1}>הבא ›</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
