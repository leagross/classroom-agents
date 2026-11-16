import { API_BASE, authHeaders } from "./client";

/** Slides for one activity. The server builds them on first request and
 *  caches them, so calling this again for the same activity is cheap. */
export async function fetchActivitySlides(sessionId, activityIndex) {
  const res = await fetch(`${API_BASE}/api/session/${sessionId}/slides/${activityIndex}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "slides unavailable");
  return (await res.json()).slides;
}
