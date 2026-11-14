import { getStoredApiKey } from "./apiKey";

export const API_BASE = "";

export function authHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const key = getStoredApiKey();
  if (key) headers["X-Anthropic-Key"] = key;
  return headers;
}

/**
 * Shared SSE consumer for any POST endpoint that streams
 * {type: "start"|"token"|"end"|"done"|"error", ...} events, one per line
 * prefixed "data: ". Used by both chat.js (sendMessageStream) and
 * lessonPlan.js (continueLessonStream) — any new streaming endpoint should
 * reuse this instead of growing its own SSE parsing.
 */
export async function streamSSE(url, body, onEvent, genericErrorDetail) {
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
