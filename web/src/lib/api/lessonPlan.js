import { API_BASE, authHeaders, streamSSE } from "./client";

/**
 * Generates a lesson plan preview — no session/DB row is created yet.
 * `profile` is stage 1's output (time, depth, level, goal); the server
 * refuses to build a plan without a complete one.
 */
export async function generateLessonPlan(topic, poolKeys, profile) {
  const body = { topic, profile };
  if (poolKeys && poolKeys.length === 2) body.pool_keys = poolKeys;
  const res = await fetch(API_BASE + "/api/lesson-plan", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "lesson plan generation failed");
  return data; // { plan, pool }
}

/**
 * Produces exactly one autonomous "beat" of a plan-driven lesson (no new
 * user text). onEvent receives the same event shape as sendMessageStream;
 * its final "done" event carries {continue, awaiting_user, activity_index}.
 */
export async function continueLessonStream(sessionId, onEvent) {
  await streamSSE(
    "/api/session/" + sessionId + "/continue/stream",
    {},
    onEvent,
    "משהו השתבש בהמשך השיעור האוטומטי."
  );
}
