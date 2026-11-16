/**
 * The "recent lessons in this browser" list.
 *
 * This used to be exported from Sidebar.jsx, which meant Classroom.jsx
 * imported a component module just to write to localStorage — a page
 * reaching into a sibling component's internals. Storage is not a
 * component's concern, so it lives here and both of them import it.
 *
 * It is deliberately separate from the server-side lesson list: a signed-out
 * user still gets to find their way back to a lesson they started.
 */

const STORAGE_KEY = "classroom_recent_lessons";
const MAX_ENTRIES = 15;

export function getRecentLessons() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    // Corrupt or unavailable storage must not take the sidebar down with it.
    return [];
  }
}

export function saveRecentLesson(id, topic, poolNames) {
  const list = [{ id, topic, poolNames, ts: Date.now() }, ...getRecentLessons().filter((l) => l.id !== id)];
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_ENTRIES)));
  } catch {
    /* private mode / quota — the lesson itself still works */
  }
}

export function removeRecentLesson(id) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(getRecentLessons().filter((l) => l.id !== id)));
  } catch {
    /* as above */
  }
}
