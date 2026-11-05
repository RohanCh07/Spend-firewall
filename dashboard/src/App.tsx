import { useEffect, useState } from "react";
import { AdminClient } from "spendfirewall";
import { Conn, loadConn, saveConn } from "./api";
import { Overview } from "./pages/Overview";
import { Sessions } from "./pages/Sessions";
import { Policies } from "./pages/Policies";
import { Activity } from "./pages/Activity";
import { Settings } from "./pages/Settings";

const TABS = ["overview", "sessions", "policies", "activity", "settings"] as const;
type Tab = (typeof TABS)[number];

function tabFromHash(): Tab {
  const h = location.hash.replace("#", "") as Tab;
  return TABS.includes(h) ? h : "overview";
}

export function App() {
  const [conn, setConn] = useState<Conn | null>(loadConn());
  const [tab, setTab] = useState<Tab>(tabFromHash());
  const [tenant, setTenant] = useState("");

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    if (!conn) return;
    new AdminClient(conn.url, conn.key)
      .me()
      .then((m) => setTenant(m.tenant.name))
      .catch(() => setTenant(""));
  }, [conn]);

  if (!conn)
    return (
      <Login
        onConnect={(c) => {
          saveConn(c);
          setConn(c);
        }}
      />
    );

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>◆</span> Spend Firewall
          {tenant && <span className="tenant">{tenant}</span>}
        </div>
        <nav>
          {TABS.map((t) => (
            <a key={t} href={`#${t}`} className={t === tab ? "active" : ""}>
              {t[0].toUpperCase() + t.slice(1)}
            </a>
          ))}
        </nav>
        <button
          className="ghost"
          onClick={() => {
            saveConn(null);
            setConn(null);
          }}
        >
          Sign out
        </button>
      </header>
      <main>
        {tab === "overview" && <Overview conn={conn} />}
        {tab === "sessions" && <Sessions conn={conn} />}
        {tab === "policies" && <Policies conn={conn} />}
        {tab === "activity" && <Activity conn={conn} />}
        {tab === "settings" && <Settings conn={conn} />}
      </main>
    </div>
  );
}

function Login({ onConnect }: { onConnect: (c: Conn) => void }) {
  const [url, setUrl] = useState("http://localhost:8080");
  const [key, setKey] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await new AdminClient(url, key).me();
      onConnect({ url, key });
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login">
      <form onSubmit={submit} className="card">
        <h1>
          <span className="logo">◆</span> Spend Firewall
        </h1>
        <p className="muted">Connect to your gateway with an admin key.</p>
        <label>
          Gateway URL
          <input value={url} onChange={(e) => setUrl(e.target.value)} required />
        </label>
        <label>
          Admin key
          <input value={key} onChange={(e) => setKey(e.target.value)} type="password" placeholder="sf-..." required />
        </label>
        {err && <div className="error">{err}</div>}
        <button disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
      </form>
    </div>
  );
}
