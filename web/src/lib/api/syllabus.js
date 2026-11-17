import { API_BASE, authHeaders } from "./client";

export async function generateSyllabus(topic, profile) {
  const res = await fetch(API_BASE + "/api/syllabus", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ topic, profile }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "syllabus generation failed");
  return data; // { topic, lessons, profile }
}

export async function createSyllabus(topic, lessons, profile) {
  const res = await fetch(API_BASE + "/api/syllabus/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, lessons, profile }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "syllabus creation failed");
  return data; // { id, topic, lessons }
}

export async function getSyllabus(id) {
  const res = await fetch(API_BASE + "/api/syllabus/" + id);
  if (!res.ok) throw new Error("syllabus not found");
  return res.json();
}

export async function getMySyllabi() {
  const res = await fetch(API_BASE + "/api/syllabi");
  if (!res.ok) return [];
  return (await res.json()).syllabi;
}

export async function generateSyllabusLessonPlan(syllabusId, lessonIndex) {
  const res = await fetch(API_BASE + `/api/syllabus/${syllabusId}/lesson/${lessonIndex}/plan`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "lesson plan generation failed");
  return data; // { topic, plan, pool }
}
