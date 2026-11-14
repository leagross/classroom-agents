import { useEffect, useRef, useState } from "react";
import { continueLessonStream } from "../lib/api/lessonPlan";

const AUTO_CONTINUE_DELAY_MS = 1500;
const MAX_AUTO_CONTINUE_ITERATIONS = 8; // safety cap against a runaway loop

/**
 * Drives the semi-autonomous side of a plan-driven lesson: once a session
 * with a plan isn't waiting on the student, this keeps calling
 * continueLessonStream in a paced loop until the lesson pauses again
 * (awaiting_user) or the student sends a message, which always pre-empts a
 * scheduled beat (see preempt()).
 *
 * `runStream` is the caller's existing helper that wires SSE events into the
 * chat UI and resolves with the final "done" event — this hook only decides
 * *when* to call it again, not how a beat is rendered. A plan-less ("review")
 * session never schedules anything, since `plan` stays falsy throughout.
 */
export default function useLessonAutoplay({ sessionId, plan, initialActivityIndex, initialAwaitingUser, runStream }) {
  const [activityIndex, setActivityIndex] = useState(initialActivityIndex || 0);
  const tokenRef = useRef({ cancelled: true });

  useEffect(() => {
    setActivityIndex(initialActivityIndex || 0);
    tokenRef.current.cancelled = true;
    const token = { cancelled: false };
    tokenRef.current = token;
    if (plan && !initialAwaitingUser) {
      scheduleNext(token, 0);
    }
    return () => { token.cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  function scheduleNext(token, iteration) {
    if (!plan || token.cancelled || iteration >= MAX_AUTO_CONTINUE_ITERATIONS) return;
    setTimeout(() => runBeat(token, iteration), AUTO_CONTINUE_DELAY_MS);
  }

  async function runBeat(token, iteration) {
    if (token.cancelled) return;
    const doneEvent = await runStream((onEvent) => continueLessonStream(sessionId, onEvent));
    if (token.cancelled || !doneEvent) return;
    if (typeof doneEvent.activity_index === "number") setActivityIndex(doneEvent.activity_index);
    if (doneEvent.continue) scheduleNext(token, iteration + 1);
  }

  /** The user taking their turn always wins over a scheduled autonomous beat. */
  function preempt() {
    tokenRef.current.cancelled = true;
    const token = { cancelled: false };
    tokenRef.current = token;
    return token;
  }

  /** Call after a normal user-message stream's "done" event, with the token preempt() returned. */
  function handleDone(doneEvent, token) {
    if (doneEvent && typeof doneEvent.activity_index === "number") setActivityIndex(doneEvent.activity_index);
    if (doneEvent && doneEvent.continue) scheduleNext(token, 0);
  }

  return { activityIndex, preempt, handleDone };
}
