import { API_BASE, authHeaders } from "./client";

/** 1.3: a short quiz to place a student who isn't sure of their level.
 *  The right answers stay on the server — these questions carry none. */
export async function startDiagnostic(topic) {
  const res = await fetch(API_BASE + "/api/intake/diagnostic", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ topic }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "לא הצלחתי לבנות בוחן אבחון.");
  return data; // { id, questions: [{ question, options, difficulty }] }
}

/** answers: one option index per question, null where the student skipped. */
export async function gradeDiagnostic(id, answers) {
  const res = await fetch(`${API_BASE}/api/intake/diagnostic/${id}/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "לא הצלחתי לבדוק את הבוחן.");
  return data; // { level, correct, total }
}
