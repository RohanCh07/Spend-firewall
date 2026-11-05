import { useState } from "react";
import type { Policy, PolicyInput, Scope, Window } from "spendfirewall";
import { Conn, client, usd, usePoll } from "../api";
import { Meter } from "./Sessions";

const SCOPES: Scope[] = ["session", "agent", "customer", "tenant"];
const WINDOWS: Window[] = ["total", "minute", "hour", "day", "month"];
const SCOPE_HELP: Record<Scope, string> = {
  session: "each session gets this budget",
  agent: "each agent gets this budget",
  customer: "each customer gets this budget",
  tenant: "everything on this account, combined",
};

export function Policies({ conn }: { conn: Conn }) {
  const { data, error, reload } = usePoll(() => client(conn).policies(), [conn], 15000);
  const budgets = usePoll(() => client(conn).budgets(), [conn], 5000);
  const [editing, setEditing] = useState<Policy | null>(null);
  const [err, setErr] = useState("");

  const live = new Map((budgets.data ?? []).map((b) => [b.policy_id, b]));

  const act = async (fn: () => Promise<unknown>) => {
    setErr("");
    try {
      await fn();
      await reload();
      await budgets.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section>
      <h2>Budgets</h2>
      <p className="muted">
        A call is blocked before it reaches the provider if it would push <em>any</em> matching budget over its limit.
      </p>
      {(error || err) && <div className="error">{error || err}</div>}
      <PolicyForm
        key={editing?.id ?? "new"}
        initial={editing}
        onCancel={() => setEditing(null)}
        onSave={(p) =>
          act(async () => {
            if (editing) await client(conn).updatePolicy(editing.id, { name: p.name, limit_usd: p.limit_usd, window: p.window });
            else await client(conn).createPolicy(p);
            setEditing(null);
          })
        }
      />
      <div className="card flush">
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>Applies to</th>
              <th>Window</th>
              <th className="num">Limit</th>
              <th>Current</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((p) => {
              const b = live.get(p.id);
              return (
                <tr key={p.id} className={p.enabled ? "" : "disabled"}>
                  <td>{p.name}</td>
                  <td>
                    {p.scope}
                    {p.scope_id ? (
                      <span className="mono"> = {p.scope_id}</span>
                    ) : p.scope === "tenant" ? (
                      <span className="muted"> (whole account)</span>
                    ) : (
                      <span className="muted"> (each)</span>
                    )}
                  </td>
                  <td>{p.window}</td>
                  <td className="num">{usd(p.limit_usd)}</td>
                  <td>{b ? <Meter pct={b.pct} /> : <span className="muted small">per {p.scope}, see Sessions</span>}</td>
                  <td>
                    <input type="checkbox" checked={p.enabled} onChange={(e) => act(() => client(conn).updatePolicy(p.id, { enabled: e.target.checked }))} />
                  </td>
                  <td className="actions">
                    <button className="ghost" onClick={() => setEditing(p)}>Edit</button>
                    <button className="ghost danger-text" onClick={() => act(() => client(conn).deletePolicy(p.id))}>Delete</button>
                  </td>
                </tr>
              );
            })}
            {data?.length === 0 && (
              <tr>
                <td colSpan={7} className="muted center">No budgets yet. Without one, calls are tracked but never blocked for cost.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PolicyForm({ initial, onSave, onCancel }: { initial: Policy | null; onSave: (p: PolicyInput) => void; onCancel: () => void }) {
  const [name, setName] = useState(initial?.name ?? "");
  const [scope, setScope] = useState<Scope>(initial?.scope ?? "session");
  const [scopeId, setScopeId] = useState(initial?.scope_id ?? "");
  const [window, setWindow] = useState<Window>(initial?.window ?? "total");
  const [limit, setLimit] = useState(String(initial?.limit_usd ?? "5"));

  return (
    <form
      className="card form-row"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ name, scope, scope_id: scope === "tenant" || !scopeId ? null : scopeId, window, limit_usd: Number(limit) });
        if (!initial) setName("");
      }}
    >
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="per-session cap" required />
      </label>
      <label>
        Scope
        <select value={scope} onChange={(e) => setScope(e.target.value as Scope)} disabled={!!initial}>
          {SCOPES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      {scope !== "tenant" && (
        <label>
          Only this id <span className="muted">(optional)</span>
          <input value={scopeId} onChange={(e) => setScopeId(e.target.value)} placeholder={`every ${scope}`} disabled={!!initial} />
        </label>
      )}
      <label>
        Window
        <select value={window} onChange={(e) => setWindow(e.target.value as Window)}>
          {WINDOWS.map((w) => <option key={w}>{w}</option>)}
        </select>
      </label>
      <label>
        Limit (USD)
        <input type="number" min="0.000001" step="any" value={limit} onChange={(e) => setLimit(e.target.value)} required />
      </label>
      <div className="form-actions">
        <button>{initial ? "Save" : "Add budget"}</button>
        {initial && <button type="button" className="ghost" onClick={onCancel}>Cancel</button>}
      </div>
      <div className="muted small full">{SCOPE_HELP[scope]}{scopeId && scope !== "tenant" ? `, only for ${scopeId}` : ""}</div>
    </form>
  );
}
