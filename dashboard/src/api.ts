import { useCallback, useEffect, useRef, useState } from "react";
import { AdminClient } from "spendfirewall";

const STORE = "spendfirewall.conn";

export interface Conn {
  url: string;
  key: string;
}

export function loadConn(): Conn | null {
  try {
    const raw = localStorage.getItem(STORE);
    return raw ? (JSON.parse(raw) as Conn) : null;
  } catch {
    return null;
  }
}

export function saveConn(c: Conn | null) {
  try {
    if (c) localStorage.setItem(STORE, JSON.stringify(c));
    else localStorage.removeItem(STORE);
  } catch {
    /* storage unavailable */
  }
}

export const client = (c: Conn) => new AdminClient(c.url, c.key);

/** Fetch now, then poll. Returns data, error and a manual reload. */
export function usePoll<T>(fn: () => Promise<T>, deps: unknown[], intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    reload();
    const t = setInterval(reload, intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, reload };
}

export const usd = (v: number) => (v >= 1 ? `$${v.toFixed(2)}` : v >= 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(5)}`);

export const ago = (iso: string) => {
  const s = (Date.now() - new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z").getTime()) / 1000;
  if (s < 60) return `${Math.max(0, Math.round(s))}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

export const DECISION_LABEL: Record<string, string> = {
  allowed: "Allowed",
  budget_exceeded: "Budget",
  loop_detected: "Loop",
  session_killed: "Killed",
  agent_killed: "Killed",
  customer_killed: "Killed",
  killed_mid_stream: "Killed mid-stream",
  upstream_error: "Provider error",
  unknown_model: "Unknown model",
  identity_required: "No identity",
  firewall_unavailable: "Firewall down",
};
