import { useState } from "react";
import { Conn, DECISION_LABEL, ago, client, usd, usePoll } from "../api";

export function Activity({ conn }: { conn: Conn }) {
  const [blockedOnly, setBlockedOnly] = useState(false);
  const events = usePoll(() => client(conn).events({ limit: 200, blocked_only: blockedOnly }), [conn, blockedOnly], 3000);
  const alerts = usePoll(() => client(conn).alerts(20), [conn], 10000);

  return (
    <section>
      <h2>Alerts</h2>
      <div className="card flush">
        <table className="data">
          <thead>
            <tr>
              <th>When</th>
              <th>Budget</th>
              <th>For</th>
              <th>Threshold</th>
              <th className="num">Spent / limit</th>
            </tr>
          </thead>
          <tbody>
            {(alerts.data ?? []).map((a) => (
              <tr key={a.id}>
                <td className="muted">{ago(a.fired_at)}</td>
                <td>{a.policy ?? a.policy_id}</td>
                <td className="mono">{a.scope_id}</td>
                <td>
                  <span className={`pill ${a.threshold >= 100 ? "bad" : a.threshold >= 80 ? "warn" : "ok"}`}>{a.threshold}%</span>
                </td>
                <td className="num">
                  {usd(a.spent_usd)} / {usd(a.limit_usd)}
                </td>
              </tr>
            ))}
            {alerts.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="muted center">No alerts yet. They fire at 50, 80 and 100% of a budget.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="row between">
        <h2>Recent calls</h2>
        <label className="check">
          <input type="checkbox" checked={blockedOnly} onChange={(e) => setBlockedOnly(e.target.checked)} /> Blocked only
        </label>
      </div>
      {events.error && <div className="error">{events.error}</div>}
      <div className="card flush">
        <table className="data">
          <thead>
            <tr>
              <th>When</th>
              <th>Decision</th>
              <th>Session</th>
              <th>Agent</th>
              <th>Model</th>
              <th className="num">Tokens in/out</th>
              <th className="num">Cost</th>
              <th className="num">Latency</th>
              <th className="num">Overhead</th>
            </tr>
          </thead>
          <tbody>
            {(events.data ?? []).map((e) => (
              <tr key={e.id}>
                <td className="muted">{ago(e.ts)}</td>
                <td>
                  <span className={`pill ${e.decision === "allowed" ? "ok" : "bad"}`}>{DECISION_LABEL[e.decision] ?? e.decision}</span>
                  {e.stream && <span className="pill">stream</span>}
                </td>
                <td className="mono trunc">{e.session_id ?? "—"}</td>
                <td className="mono trunc">{e.agent_id ?? "—"}</td>
                <td className="mono">{e.model}</td>
                <td className="num">
                  {e.input_tokens} / {e.output_tokens}
                </td>
                <td className="num">{usd(e.cost_usd)}</td>
                <td className="num">{e.latency_ms} ms</td>
                <td className="num muted">{e.overhead_ms.toFixed(2)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
