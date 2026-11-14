import { API_BASE } from "./client";

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
