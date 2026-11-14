import { API_BASE } from "./client";

export async function getDashboard() {
  const res = await fetch(API_BASE + "/api/dashboard");
  if (!res.ok) return null;
  return res.json();
}
