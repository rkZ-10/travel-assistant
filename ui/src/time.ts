import { useEffect, useState } from "react";

/** Minutes left until `fetchedAt + validMinutes` (negative once expired). Re-renders every 15s. */
export function useMinutesLeft(fetchedAt: string | null | undefined, validMinutes: number): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);
  if (!fetchedAt) return null;
  const expires = new Date(fetchedAt).getTime() + validMinutes * 60_000;
  return Math.floor((expires - now) / 60_000);
}

export const clock = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

export const hhmm = (local: string) => local.slice(-5); // "2026-10-17 07:05" -> "07:05"

export const duration = (min: number) => `${Math.floor(min / 60)}h ${min % 60}m`;

export const inr = (n?: number | null) => (n == null ? "—" : `₹${n.toLocaleString("en-IN")}`);
