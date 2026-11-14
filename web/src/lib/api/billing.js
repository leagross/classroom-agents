import { API_BASE } from "./client";

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
