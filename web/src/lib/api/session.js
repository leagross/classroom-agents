import { API_BASE } from "./client";

export async function getAgents() {
  const res = await fetch(API_BASE + "/api/agents");
  return res.json();
}

export async function createSession(topic, poolKeys, plan, syllabusMeta) {
  const body = { topic };
  if (poolKeys && poolKeys.length === 2) body.pool_keys = poolKeys;
  if (plan) body.plan = plan;
  if (syllabusMeta?.syllabusId != null && syllabusMeta?.lessonIndex != null) {
    body.syllabus_id = syllabusMeta.syllabusId;
    body.syllabus_lesson_index = syllabusMeta.lessonIndex;
  }
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

export async function deleteSession(id) {
  await fetch(API_BASE + "/api/session/" + id, { method: "DELETE" });
}
