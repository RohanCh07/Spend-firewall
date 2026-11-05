import type { Session } from "spendfirewall";
import { type Config, clientFor, loadConfig, saveConfig } from "./config";
import { ago, money, originPattern } from "./format";

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

function esc(s: string | null | undefined): string {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

async function main() {
  const cfg = await loadConfig();
  if (!cfg) return showSetup();
  showMain(cfg);
}

function showSetup(prefill?: Partial<Config>) {
  $("#setup").hidden = false;
  $("#main").hidden = true;
  const form = $<HTMLFormElement>("#setup-form");
  ($<HTMLInputElement>("#gw")).value = prefill?.gatewayUrl ?? "http://localhost:8080";
  ($<HTMLInputElement>("#dash")).value = prefill?.dashboardUrl ?? "http://localhost:5173";
  form.onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#setup-error");
    err.textContent = "";
    const c: Config = {
      gatewayUrl: $<HTMLInputElement>("#gw").value.trim(),
      adminKey: $<HTMLInputElement>("#key").value.trim(),
      dashboardUrl: $<HTMLInputElement>("#dash").value.trim(),
    };
    try {
      // Ask for access to just the gateway's origin (must run in the click handler).
      const granted = await chrome.permissions.request({ origins: [originPattern(c.gatewayUrl)] });
      if (!granted) throw new Error("Permission to reach the gateway was declined");
      await clientFor(c).me();
      await saveConfig(c);
      chrome.runtime.sendMessage("poll");
      showMain(c);
    } catch (x) {
      err.textContent = x instanceof Error ? x.message : String(x);
    }
  };
}

async function showMain(cfg: Config) {
  $("#setup").hidden = true;
  $("#main").hidden = false;
  $<HTMLAnchorElement>("#open-dash").onclick = (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: cfg.dashboardUrl });
  };
  $("#signout").onclick = async () => {
    await saveConfig(null);
    chrome.runtime.sendMessage("poll");
    showSetup(cfg);
  };
  await render(cfg);
}

async function render(cfg: Config) {
  const api = clientFor(cfg);
  const status = $("#status");
  try {
    const [me, sum, sessions] = await Promise.all([api.me(), api.summary(24), api.sessions({ hours: 24, limit: 50 })]);
    status.textContent = "";
    $("#tenant").textContent = me.tenant.name;
    $("#spend").textContent = money(sum.total_cost_usd);
    $("#calls").textContent = sum.calls.toLocaleString();
    $("#blocked").textContent = sum.blocked.toLocaleString();
    $("#blocked").classList.toggle("bad", sum.blocked > 0);
    renderSessions(cfg, sessions);
  } catch (e) {
    status.textContent = `Can't reach the gateway: ${e instanceof Error ? e.message : e}`;
  }
}

function renderSessions(cfg: Config, sessions: Session[]) {
  const live = sessions.filter((s) => s.live || s.killed).slice(0, 15);
  const list = $("#sessions");
  if (!live.length) {
    list.innerHTML = `<li class="empty">No live sessions right now.</li>`;
    return;
  }
  list.innerHTML = live
    .map(
      (s) => `
      <li class="${s.killed ? "killed" : ""}">
        <div class="who">
          <div class="mono">${esc(s.session_id)}</div>
          <div class="sub">${esc(s.agent_id ?? "no agent")} · ${s.calls} calls · ${ago(s.last_seen)} ago${
            s.budget_pct !== null ? ` · ${s.budget_pct.toFixed(0)}%` : ""
          }</div>
        </div>
        <div class="amt">${money(s.cost_usd)}</div>
        <button data-id="${esc(s.session_id)}" data-killed="${s.killed}" class="${s.killed ? "ghost" : "kill"}">
          ${s.killed ? "Revive" : "Kill"}
        </button>
      </li>`,
    )
    .join("");
  list.querySelectorAll<HTMLButtonElement>("button[data-id]").forEach((b) => {
    b.onclick = async () => {
      b.disabled = true;
      const api = clientFor(cfg);
      if (b.dataset.killed === "true") await api.unkill("session", b.dataset.id!);
      else await api.kill("session", b.dataset.id!, "killed from browser extension");
      await render(cfg);
    };
  });
}

main();
