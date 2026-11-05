import { useEffect, useState } from "react";
import type { Tenant } from "spendfirewall";
import { Conn, ago, client, usePoll } from "../api";

export function Settings({ conn }: { conn: Conn }) {
  const me = usePoll(() => client(conn).me(), [conn], 60000);
  const keys = usePoll(() => client(conn).keys(), [conn], 60000);
  const [t, setT] = useState<Tenant | null>(null);
  const [msg, setMsg] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [keyName, setKeyName] = useState("");
  const [keyRole, setKeyRole] = useState<"proxy" | "admin">("proxy");

  useEffect(() => {
    if (me.data && !t) setT(me.data.tenant);
  }, [me.data, t]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!t) return;
    setMsg("");
    try {
      const { id: _id, ...rest } = t;
      const saved = await client(conn).updateSettings({ ...rest, slack_webhook_url: rest.slack_webhook_url || "", alert_email: rest.alert_email || null });
      setT(saved);
      setMsg("Saved");
    } catch (x) {
      setMsg(x instanceof Error ? x.message : String(x));
    }
  };

  return (
    <section>
      <h2>Firewall settings</h2>
      {t && (
        <form className="card settings" onSubmit={save}>
          <label>
            Name
            <input value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
          </label>
          <label>
            If the firewall's Redis is down
            <select value={t.fail_mode} onChange={(e) => setT({ ...t, fail_mode: e.target.value as "open" | "closed" })}>
              <option value="closed">Fail closed: block calls (no overspend possible)</option>
              <option value="open">Fail open: allow calls unenforced (no downtime)</option>
            </select>
          </label>
          <label>
            Loop detection: block after this many identical calls
            <input type="number" min={0} value={t.loop_max_repeats} onChange={(e) => setT({ ...t, loop_max_repeats: Number(e.target.value) })} />
            <span className="muted small">0 turns loop detection off</span>
          </label>
          <label>
            …within this many seconds
            <input type="number" min={1} value={t.loop_window_seconds} onChange={(e) => setT({ ...t, loop_window_seconds: Number(e.target.value) })} />
          </label>
          <label className="check">
            <input type="checkbox" checked={t.require_identity} onChange={(e) => setT({ ...t, require_identity: e.target.checked })} />
            Reject calls without X-Agent-Id and X-Session-Id
          </label>
          <label>
            Slack webhook URL for alerts
            <input value={t.slack_webhook_url ?? ""} onChange={(e) => setT({ ...t, slack_webhook_url: e.target.value })} placeholder="https://hooks.slack.com/services/…" />
          </label>
          <label>
            Alert email
            <input type="email" value={t.alert_email ?? ""} onChange={(e) => setT({ ...t, alert_email: e.target.value })} />
          </label>
          <div className="row">
            <button>Save settings</button>
            {msg && <span className="muted">{msg}</span>}
          </div>
        </form>
      )}

      <h2>API keys</h2>
      <p className="muted">
        Give agents <b>proxy</b> keys (they can only make LLM calls). <b>Admin</b> keys can change budgets and kill sessions.
      </p>
      {newKey && (
        <div className="card notice">
          New key, shown once: <code className="select">{newKey}</code>
        </div>
      )}
      <form
        className="card form-row"
        onSubmit={async (e) => {
          e.preventDefault();
          const k = await client(conn).createKey(keyName, keyRole);
          setNewKey(k.key);
          setKeyName("");
          keys.reload();
        }}
      >
        <label>
          Name
          <input value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="support-bot prod" />
        </label>
        <label>
          Role
          <select value={keyRole} onChange={(e) => setKeyRole(e.target.value as "proxy" | "admin")}>
            <option value="proxy">proxy</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <div className="form-actions">
          <button>Create key</button>
        </div>
      </form>
      <div className="card flush">
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>Key</th>
              <th>Role</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(keys.data ?? []).map((k) => (
              <tr key={k.id} className={k.revoked ? "disabled" : ""}>
                <td>{k.name}</td>
                <td className="mono">{k.prefix}…</td>
                <td>{k.role}</td>
                <td className="muted">{ago(k.created_at)}</td>
                <td>
                  {k.revoked ? (
                    <span className="muted">revoked</span>
                  ) : (
                    <button className="ghost danger-text" onClick={async () => { await client(conn).revokeKey(k.id); keys.reload(); }}>
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
