import { useState } from "react";
import type { Session } from "spendfirewall";
import { Conn, ago, client, usd, usePoll } from "../api";

export function Sessions({ conn }: { conn: Conn }) {
  const [liveOnly, setLiveOnly] = useState(false);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const { data, error, reload } = usePoll(() => client(conn).sessions({ hours: 24 * 7, limit: 500 }), [conn], 3000);

  const rows = (data ?? []).filter(
    (s) =>
      (!liveOnly || s.live) &&
      (!filter || [s.session_id, s.agent_id, s.customer_id].some((v) => v?.toLowerCase().includes(filter.toLowerCase()))),
  );

  const toggle = async (s: Session) => {
    setBusy(s.session_id);
    try {
      if (s.killed) await client(conn).unkill("session", s.session_id);
      else await client(conn).kill("session", s.session_id, "killed from dashboard");
      await reload();
    } finally {
      setBusy(null);
    }
  };

  return (
    <section>
      <div className="row between">
        <h2>Sessions</h2>
        <div className="row">
          <input placeholder="Filter by session, agent, customer" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={liveOnly} onChange={(e) => setLiveOnly(e.target.checked)} /> Live only
          </label>
        </div>
      </div>
      <p className="muted">
        Killing a session blocks its next call (and cuts a live stream) without touching other sessions on the same key.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="card flush">
        <table className="data">
          <thead>
            <tr>
              <th>Session</th>
              <th>Agent</th>
              <th>Customer</th>
              <th className="num">Calls</th>
              <th className="num">Blocked</th>
              <th className="num">Spend</th>
              <th>Budget</th>
              <th>Last seen</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.session_id} className={s.killed ? "killed" : ""}>
                <td className="mono">
                  {s.live && <span className="dot" title="active in last 5 min" />}
                  {s.session_id}
                </td>
                <td className="mono">{s.agent_id ?? "—"}</td>
                <td className="mono">{s.customer_id ?? "—"}</td>
                <td className="num">{s.calls}</td>
                <td className="num">{s.blocked ? <span className="pill bad">{s.blocked}</span> : 0}</td>
                <td className="num">{usd(s.cost_usd)}</td>
                <td>{s.budget_pct === null ? <span className="muted">no budget</span> : <Meter pct={s.budget_pct} />}</td>
                <td className="muted">{ago(s.last_seen)}</td>
                <td>
                  <button className={s.killed ? "ghost" : "ghost danger-text"} disabled={busy === s.session_id} onClick={() => toggle(s)}>
                    {s.killed ? "Revive" : "Kill"}
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="muted center">
                  No sessions. Tag requests with an <code>X-Session-Id</code> header.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Meter({ pct }: { pct: number }) {
  const tone = pct >= 100 ? "bad" : pct >= 80 ? "warn" : "ok";
  return (
    <div className="meter" title={`${pct}%`}>
      <div className={`fill ${tone}`} style={{ width: `${Math.min(100, pct)}%` }} />
      <span>{pct.toFixed(0)}%</span>
    </div>
  );
}
