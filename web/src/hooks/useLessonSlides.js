import { useCallback, useEffect, useRef, useState } from "react";
import { fetchActivitySlides } from "../lib/api/slides";

/**
 * The slide deck that accompanies the activity being taught.
 *
 * Fetched per activity and only once — the server caches too, but a second
 * request per activity would still cost a round trip and could race with
 * the first. Slides are a companion to the lesson, never a blocker: if the
 * deck fails to build, the board simply stays on the written notes and the
 * lesson carries on.
 */
export default function useLessonSlides({ sessionId, activityIndex, enabled }) {
  const [deck, setDeck] = useState([]);
  const [slideIndex, setSlideIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const requested = useRef(new Set());

  useEffect(() => {
    requested.current = new Set();
    setDeck([]);
    setSlideIndex(0);
    setFailed(false);
  }, [sessionId]);

  useEffect(() => {
    if (!enabled || activityIndex == null || !sessionId) return;
    if (requested.current.has(activityIndex)) return;
    requested.current.add(activityIndex);

    let cancelled = false;
    setLoading(true);
    setFailed(false);
    fetchActivitySlides(sessionId, activityIndex)
      .then((slides) => {
        if (cancelled) return;
        setDeck(slides || []);
        setSlideIndex(0);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, activityIndex, enabled]);

  const goTo = useCallback(
    (index) => setSlideIndex((prev) => Math.max(0, Math.min(deck.length - 1, index ?? prev))),
    [deck.length]
  );

  return {
    deck,
    slideIndex,
    slide: deck[slideIndex] || null,
    count: deck.length,
    loading,
    failed,
    hasSlides: deck.length > 0,
    prev: () => goTo(slideIndex - 1),
    next: () => goTo(slideIndex + 1),
  };
}
