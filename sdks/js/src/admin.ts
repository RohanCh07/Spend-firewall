/** Typed client for the gateway's /v1/admin API. Works in browsers, VS Code and Node 18+. */

export type Scope = "tenant" | "agent" | "session" | "customer";
export type KillScope = "agent" | "session" | "customer";
export type Window = "total" | "minute" | "hour" | "day" | "month";

export interface Tenant {
  id: string;
  name: string;
  fail_mode: "open" | "closed";
  loop_max_repeats: number;
  loop_window_seconds: number;
  require_identity: boolean;
  slack_webhook_url: string | null;
  alert_email: string | null;
}
export interface Policy {
  id: string;
  name: string;
  scope: Scope;
  scope_id: string | null;
  window: Window;
  limit_usd: number;
  enabled: boolean;
  created_at: string;
}
export type PolicyInput = Omit<Policy, "id" | "created_at" | "enabled"> & { enabled?: boolean };
export interface PolicyFile {
  version: 1;
  settings?: Partial<Omit<Tenant, "id">>;
  budgets: PolicyInput[];
}
export interface Session {
  session_id: string;
  agent_id: string | null;
  customer_id: string | null;
  first_seen: string;
  last_seen: string;
  calls: number;
  blocked: number;
  cost_usd: number;
  budget_pct: number | null;
  killed: boolean;
  live: boolean;
}
export interface Group {
  key: string | null;
  cost_usd: number;
  calls: number;
}
export interface Summary {
  hours: number;
  total_cost_usd: number;
  calls: number;
  blocked: number;
  avg_overhead_ms: number;
  sessions: number;
  by_model: Group[];
  by_agent: Group[];
  by_customer: Group[];
  top_sessions: Group[];
  decisions: Record<string, number>;
  timeseries: { hour: string; cost_usd: number; calls: number; blocked: number }[];
}
export interface UsageEvent {
  id: number;
  ts: string;
  agent_id: string | null;
  session_id: string | null;
  customer_id: string | null;
  model: string;
  provider: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  decision: string;
  status_code: number;
  latency_ms: number;
  overhead_ms: number;
  stream: boolean;
}
export interface Alert {
  id: number;
  policy_id: string;
  policy: string | null;
  scope_id: string | null;
  threshold: number;
  spent_usd: number;
  limit_usd: number;
  fired_at: string;
}
export interface BudgetStatus {
  policy_id: string;
  name: string;
  scope: Scope;
  scope_id: string;
  window: Window;
  limit_usd: number;
  spent_usd: number;
  pct: number;
}
export interface Kill {
  id: string;
  scope: KillScope;
  scope_id: string;
  reason: string;
  created_at: string;
}
export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  role: "proxy" | "admin";
  revoked: boolean;
  created_at: string;
}

export class FirewallApiError extends Error {
  constructor(public status: number, public type: string, message: string) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export class AdminClient {
  readonly baseUrl: string;
  constructor(gatewayUrl: string, private apiKey: string, private fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis)) {
    this.baseUrl = gatewayUrl.replace(/\/+$/, "").replace(/\/v1$/, "");
  }

  private async req<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
    const url = new URL(`${this.baseUrl}/v1/admin${path}`);
    for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    const r = await this.fetchImpl(url.toString(), {
      method,
      headers: { authorization: `Bearer ${this.apiKey}`, ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (r.status === 204) return undefined as T;
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = (data as { error?: { type?: string; message?: string }; detail?: unknown }).error;
      throw new FirewallApiError(r.status, err?.type ?? "http_error", err?.message ?? JSON.stringify(data));
    }
    return data as T;
  }

  me() { return this.req<{ tenant: Tenant; role: string }>("GET", "/me"); }
  updateSettings(s: Partial<Omit<Tenant, "id">>) { return this.req<Tenant>("PATCH", "/settings", s); }

  policies() { return this.req<Policy[]>("GET", "/policies"); }
  createPolicy(p: PolicyInput) { return this.req<Policy>("POST", "/policies", p); }
  updatePolicy(id: string, p: Partial<Pick<Policy, "name" | "limit_usd" | "enabled" | "window">>) {
    return this.req<Policy>("PATCH", `/policies/${id}`, p);
  }
  deletePolicy(id: string) { return this.req<void>("DELETE", `/policies/${id}`); }
  syncPolicies(file: PolicyFile) {
    return this.req<{ created: number; updated: number; disabled: number }>("PUT", "/policies", file);
  }
  budgets(scopeId?: string) { return this.req<BudgetStatus[]>("GET", "/budgets", undefined, { scope_id: scopeId }); }

  kill(scope: KillScope, scopeId: string, reason = "") { return this.req<Kill>("POST", "/kill", { scope, scope_id: scopeId, reason }); }
  unkill(scope: KillScope, scopeId: string) {
    return this.req<void>("DELETE", `/kill/${scope}/${encodeURIComponent(scopeId)}`);
  }
  kills() { return this.req<Kill[]>("GET", "/kills"); }

  sessions(q: { hours?: number; agent_id?: string; limit?: number } = {}) { return this.req<Session[]>("GET", "/sessions", undefined, q); }
  summary(hours = 24) { return this.req<Summary>("GET", "/usage/summary", undefined, { hours }); }
  events(q: { limit?: number; blocked_only?: boolean; session_id?: string } = {}) {
    return this.req<UsageEvent[]>("GET", "/events", undefined, q);
  }
  alerts(limit = 50) { return this.req<Alert[]>("GET", "/alerts", undefined, { limit }); }

  keys() { return this.req<ApiKeyInfo[]>("GET", "/keys"); }
  createKey(name: string, role: "proxy" | "admin" = "proxy") {
    return this.req<{ id: string; key: string; role: string }>("POST", "/keys", { name, role });
  }
  revokeKey(id: string) { return this.req<void>("DELETE", `/keys/${id}`); }
}
