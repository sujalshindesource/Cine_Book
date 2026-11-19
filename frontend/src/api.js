import { createContext, useContext } from "react";
export const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export async function api(path, { method = "GET", body } = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error(data.error || "Request failed (is the backend running?)");
  return data;
}
export const fmt = (iso) => new Date(iso.replace(" ", "T")).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
export const money = (n) => "₹" + Number(n).toLocaleString("en-IN");
export const seatLabel = (r, c) => String.fromCharCode(65 + Number(r)) + (Number(c) + 1);
