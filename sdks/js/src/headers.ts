export interface Identity {
  agentId?: string;
  sessionId?: string;
  customerId?: string;
}

/** Tagging headers the gateway uses to attribute and enforce spend. */
export function firewallHeaders(id: Identity): Record<string, string> {
  const h: Record<string, string> = {};
  if (id.agentId) h["X-Agent-Id"] = id.agentId;
  if (id.sessionId) h["X-Session-Id"] = id.sessionId;
  if (id.customerId) h["X-Customer-Id"] = id.customerId;
  return h;
}

export function newSessionId(prefix = "s"): string {
  const rand = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `${prefix}-${rand.replace(/-/g, "").slice(0, 16)}`;
}

/**
 * Options to spread into `new OpenAI({...})` so every call goes through the firewall.
 *
 *   const client = new OpenAI(openAIOptions({ baseURL: "http://localhost:8080/v1", apiKey, agentId: "planner" }))
 */
export function openAIOptions(opts: Identity & { baseURL: string; apiKey: string }) {
  const sessionId = opts.sessionId ?? newSessionId();
  return {
    baseURL: opts.baseURL,
    apiKey: opts.apiKey,
    defaultHeaders: firewallHeaders({ ...opts, sessionId }),
  };
}

export const BLOCK_TYPES = [
  "budget_exceeded",
  "loop_detected",
  "session_killed",
  "agent_killed",
  "customer_killed",
  "identity_required",
  "firewall_unavailable",
] as const;
export type BlockType = (typeof BLOCK_TYPES)[number];

/** True if an error thrown by an OpenAI SDK call is a firewall block (stop the agent, don't retry). */
export function isFirewallBlock(err: unknown): err is { status: number; error?: { type?: string } } {
  const e = err as { status?: number; error?: { type?: string }; code?: string };
  const t = e?.error?.type ?? e?.code;
  return typeof t === "string" && (BLOCK_TYPES as readonly string[]).includes(t);
}
