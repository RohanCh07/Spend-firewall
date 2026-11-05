import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Group } from "spendfirewall";
import { Conn, client, usd, usePoll } from "../api";

const RANGES = [
  { label: "1h", hours: 1 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
];

export function Overview({ conn }: { conn: Conn }) {
  const [hours, setHours] = useState(24);
  const { data, error } = usePoll(() => client(conn).summary(hours), [conn, hours]);

  return (
    <section>
      <div className="row between">
        <h2>Overview</h2>
        <div className="seg">
          {RANGES.map((r) => (
            <button key={r.hours} className={r.hours === hours ? "on" : ""} onClick={() => setHours(r.hours)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {data && (
        <>
          <div className="kpis">
            <Kpi label="Spend" value={usd(data.total_cost_usd)} />
            <Kpi label="Calls" value={data.calls.toLocaleString()} />
            <Kpi label="Blocked" value={data.blocked.toLocaleString()} tone={data.blocked ? "warn" : undefined} />
            <Kpi label="Sessions" value={data.sessions.toLocaleString()} />
            <Kpi label="Firewall overhead" value={`${data.avg_overhead_ms.toFixed(2)} ms`} sub="avg, before provider" />
          </div>
          <div className="card">
            <h3>Spend per hour</h3>
            {data.timeseries.length === 0 ? (
              <p className="muted">No traffic in this range yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={data.timeseries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="hour" tickFormatter={(h: string) => h.slice(11, 16)} stroke="var(--muted)" fontSize={12} />
                  <YAxis tickFormatter={(v: number) => usd(v)} stroke="var(--muted)" fontSize={12} width={72} />
                  <Tooltip
                    formatter={(v: number) => usd(v)}
                    labelFormatter={(h: string) => h.replace("T", " ").slice(0, 16)}
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                  />
                  <Area type="monotone" dataKey="cost_usd" name="Spend" stroke="var(--accent)" fill="url(#g)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="grid2">
            <Breakdown title="By model" rows={data.by_model} total={data.total_cost_usd} />
            <Breakdown title="By agent" rows={data.by_agent} total={data.total_cost_usd} />
            <Breakdown title="Top sessions" rows={data.top_sessions} total={data.total_cost_usd} />
            <div className="card">
              <h3>Decisions</h3>
              <table>
                <tbody>
                  {Object.entries(data.decisions)
                    .sort((a, b) => b[1] - a[1])
                    .map(([d, n]) => (
                      <tr key={d}>
                        <td>
                          <span className={`pill ${d === "allowed" ? "ok" : "bad"}`}>{d}</span>
                        </td>
                        <td className="num">{n.toLocaleString()}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "warn" }) {
  return (
    <div className={`card kpi ${tone ?? ""}`}>
      <div className="muted small">{label}</div>
      <div className="big">{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

function Breakdown({ title, rows, total }: { title: string; rows: Group[]; total: number }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {rows.length === 0 && <p className="muted">Nothing yet.</p>}
      <table>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key ?? "—"}>
              <td className="mono trunc">{r.key ?? "(untagged)"}</td>
              <td className="bar-cell">
                <div className="bar" style={{ width: `${total ? (100 * r.cost_usd) / total : 0}%` }} />
              </td>
              <td className="num">{usd(r.cost_usd)}</td>
              <td className="num muted">{r.calls}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
