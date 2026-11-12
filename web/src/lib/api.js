export const API_BASE = "";

const API_KEY_STORAGE = "classroom_anthropic_api_key";

export function getStoredApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setStoredApiKey(key) {
  localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearStoredApiKey() {
  localStorage.removeItem(API_KEY_STORAGE);
}

export function authHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const key = getStoredApiKey();
  if (key) headers["X-Anthropic-Key"] = key;
  return headers;
}

export async function getAgents() {
  const res = await fetch(API_BASE + "/api/agents");
  return res.json();
}

export async function createSession(topic, poolKeys, plan) {
  const body = { topic };
  if (poolKeys && poolKeys.length === 2) body.pool_keys = poolKeys;
  if (plan) body.plan = plan;
  const res = await fetch(API_BASE + "/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "session creation failed");
  return res.json();
}

/**
 * Generates a lesson plan preview — no session/DB row is created yet.
 */
export async function generateLessonPlan(topic, poolKeys) {
  const body = { topic };
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

export async function getSession(id) {
  const res = await fetch(API_BASE + "/api/session/" + id);
  if (!res.ok) throw new Error("session not found");
  return res.json();
}

export async function getMe() {
  const res = await fetch(API_BASE + "/api/me");
  if (!res.ok) return null;
  return res.json();
}

export async function getAuthStatus() {
  const res = await fetch(API_BASE + "/api/auth-status");
  return res.json();
}

export async function getMyLessons() {
  const res = await fetch(API_BASE + "/api/lessons");
  if (!res.ok) return [];
  return (await res.json()).lessons;
}

export async function logout() {
  await fetch(API_BASE + "/auth/logout", { method: "POST" });
}

export async function fetchQuiz(sessionId) {
  const res = await fetch(API_BASE + "/api/session/" + sessionId + "/quiz", {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "quiz generation failed");
  return data.questions;
}

/**
 * Shared SSE consumer for any POST endpoint that streams
 * {type: "start"|"token"|"end"|"done"|"error", ...} events, one per line
 * prefixed "data: ". Used by both sendMessageStream and continueLessonStream.
 */
async function _streamSSE(url, body, onEvent, genericErrorDetail) {
  const res = await fetch(API_BASE + url, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    onEvent({ type: "error", detail: genericErrorDetail });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const raw of events) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch (e) { /* ignore malformed chunk */ }
    }
  }
}

/**
 * Sends a message and streams the reply via Server-Sent Events.
 * onEvent receives {type: "start"|"token"|"end"|"done"|"error", ...}.
 */
export async function sendMessageStream(sessionId, text, image, onEvent) {
  const body = { session_id: sessionId, text };
  if (image) body.image = image;
  await _streamSSE("/api/message/stream", body, onEvent, "משהו השתבש בשליחת ההודעה. נסה שוב.");
}

/**
 * Produces exactly one autonomous "beat" of a plan-driven lesson (no new
 * user text). onEvent receives the same event shape as sendMessageStream;
 * its final "done" event carries {continue, awaiting_user, activity_index}.
 */
export async function continueLessonStream(sessionId, onEvent) {
  await _streamSSE(
    "/api/session/" + sessionId + "/continue/stream",
    {},
    onEvent,
    "משהו השתבש בהמשך השיעור האוטומטי."
  );
}

/* ---------- Billing (subscriptions) ---------- */
export async function getBillingStatus() {
  const res = await fetch(API_BASE + "/api/billing/status");
  if (!res.ok) return null;
  return res.json();
}

export async function startCheckout(plan) {
  const res = await fetch(API_BASE + "/api/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "checkout failed");
  return data; // { url }
}
