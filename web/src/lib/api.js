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

export async function createSession(topic, poolKeys) {
  const body = { topic };
  if (poolKeys && poolKeys.length === 2) body.pool_keys = poolKeys;
  const res = await fetch(API_BASE + "/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "session creation failed");
  return res.json();
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
 * Sends a message and streams the reply via Server-Sent Events.
 * onEvent receives {type: "start"|"token"|"end"|"error", ...}.
 */
export async function sendMessageStream(sessionId, text, image, onEvent) {
  const body = { session_id: sessionId, text };
  if (image) body.image = image;

  const res = await fetch(API_BASE + "/api/message/stream", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    onEvent({ type: "error", detail: "משהו השתבש בשליחת ההודעה. נסה שוב." });
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
