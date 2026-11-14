import { API_BASE, authHeaders, streamSSE } from "./client";

/**
 * Sends a message and streams the reply via Server-Sent Events.
 * onEvent receives {type: "start"|"token"|"end"|"done"|"error", ...}.
 */
export async function sendMessageStream(sessionId, text, image, onEvent) {
  const body = { session_id: sessionId, text };
  if (image) body.image = image;
  await streamSSE("/api/message/stream", body, onEvent, "משהו השתבש בשליחת ההודעה. נסה שוב.");
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
