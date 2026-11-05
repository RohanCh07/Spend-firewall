import * as vscode from "vscode";
import { parse as parseYaml } from "yaml";
import { AdminClient, type Alert, type PolicyFile, type Session, type UsageEvent } from "spendfirewall";
import { defaultAgentId, mergeEnv } from "./envfile";

const SECRET_KEY = "spendfirewall.adminKey";
const POLICY_TEMPLATE = `# yaml-language-server: $schema=https://raw.githubusercontent.com/RohanCh07/Spend-firewall/main/shared/policy-schema/policy.schema.json
version: 1
settings:
  fail_mode: closed
  loop_max_repeats: 5
  loop_window_seconds: 60
budgets:
  - name: per-session
    scope: session
    window: total
    limit_usd: 2
  - name: per-agent-daily
    scope: agent
    window: day
    limit_usd: 25
`;

let client: AdminClient | null = null;
let output: vscode.OutputChannel;

const cfg = () => vscode.workspace.getConfiguration("spendfirewall");

function workspaceAgentId(): string {
  const set = cfg().get<string>("agentId");
  if (set) return set;
  return defaultAgentId(vscode.workspace.workspaceFolders?.[0]?.name ?? "workspace");
}

async function getClient(ctx: vscode.ExtensionContext): Promise<AdminClient | null> {
  if (client) return client;
  const key = await ctx.secrets.get(SECRET_KEY);
  if (!key) return null;
  client = new AdminClient(cfg().get<string>("gatewayUrl")!, key);
  return client;
}

const money = (v: number) => (v >= 1 ? `$${v.toFixed(2)}` : v >= 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(5)}`);

// ---------------------------------------------------------------- tree view
type Node = { kind: "session"; s: Session } | { kind: "event"; e: UsageEvent } | { kind: "info"; label: string };

class SessionsProvider implements vscode.TreeDataProvider<Node> {
  private emitter = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;
  sessions: Session[] = [];
  error: string | null = null;

  constructor(private ctx: vscode.ExtensionContext) {}

  async load() {
    const c = await getClient(this.ctx);
    if (!c) {
      this.sessions = [];
      this.error = null;
    } else {
      try {
        const agent = cfg().get<boolean>("onlyThisWorkspace") ? workspaceAgentId() : undefined;
        this.sessions = await c.sessions({ hours: 24, agent_id: agent, limit: 100 });
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      }
    }
    this.emitter.fire(undefined);
  }

  getTreeItem(n: Node): vscode.TreeItem {
    if (n.kind === "info") return new vscode.TreeItem(n.label);
    if (n.kind === "event") {
      const e = n.e;
      const item = new vscode.TreeItem(`${e.model} · ${money(e.cost_usd)}`);
      item.description = `${e.decision === "allowed" ? "" : e.decision + " · "}${e.input_tokens}/${e.output_tokens} tok · ${e.latency_ms} ms`;
      item.iconPath = new vscode.ThemeIcon(e.decision === "allowed" ? "pass" : "error");
      item.tooltip = new Date(e.ts).toLocaleString();
      return item;
    }
    const s = n.s;
    const item = new vscode.TreeItem(s.session_id, vscode.TreeItemCollapsibleState.Collapsed);
    const pct = s.budget_pct === null ? "" : ` · ${s.budget_pct.toFixed(0)}% of budget`;
    item.description = `${money(s.cost_usd)} · ${s.calls} calls${s.blocked ? ` · ${s.blocked} blocked` : ""}${pct}`;
    item.contextValue = s.killed ? "session-killed" : "session";
    item.iconPath = new vscode.ThemeIcon(
      s.killed ? "debug-stop" : s.live ? "pulse" : "history",
      s.killed ? new vscode.ThemeColor("errorForeground") : undefined,
    );
    item.tooltip = new vscode.MarkdownString(
      `**${s.session_id}**\n\nAgent: \`${s.agent_id ?? "-"}\`  \nCustomer: \`${s.customer_id ?? "-"}\`  \n` +
        `Spend: ${money(s.cost_usd)}  \nCalls: ${s.calls} (${s.blocked} blocked)  \n${s.killed ? "**Killed**" : s.live ? "Live" : "Idle"}`,
    );
    return item;
  }

  async getChildren(n?: Node): Promise<Node[]> {
    if (!n) {
      if (this.error) return [{ kind: "info", label: `Error: ${this.error}` }];
      if (!(await getClient(this.ctx))) return []; // shows the welcome view
      if (!this.sessions.length) return [{ kind: "info", label: `No sessions in the last 24h for ${workspaceAgentId()}` }];
      return this.sessions.map((s) => ({ kind: "session", s }));
    }
    if (n.kind === "session") {
      const c = await getClient(this.ctx);
      const evs = c ? await c.events({ session_id: n.s.session_id, limit: 25 }) : [];
      return evs.map((e) => ({ kind: "event", e }));
    }
    return [];
  }
}

// ---------------------------------------------------------------- activate
export function activate(ctx: vscode.ExtensionContext) {
  output = vscode.window.createOutputChannel("Spend Firewall");
  const tree = new SessionsProvider(ctx);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "workbench.view.extension.spendfirewall";
  ctx.subscriptions.push(output, status, vscode.window.registerTreeDataProvider("spendfirewall.sessions", tree));

  const seenAlerts = new Set<number>();
  let firstAlertPoll = true;

  async function refresh() {
    await tree.load();
    const c = await getClient(ctx);
    if (!c) {
      status.text = "$(shield) Spend Firewall: sign in";
      status.command = "spendfirewall.signIn";
      status.show();
      return;
    }
    status.command = "workbench.view.extension.spendfirewall";
    try {
      const sum = await c.summary(24);
      const agent = workspaceAgentId();
      const mine = sum.by_agent.find((g) => g.key === agent);
      status.text = `$(shield) ${money(mine?.cost_usd ?? 0)} today`;
      status.tooltip = `Spend Firewall\nThis workspace (${agent}): ${money(mine?.cost_usd ?? 0)} in 24h\nAll agents: ${money(sum.total_cost_usd)} · ${sum.blocked} blocked`;
      status.backgroundColor = tree.sessions.some((s) => s.blocked > 0 && s.live)
        ? new vscode.ThemeColor("statusBarItem.warningBackground")
        : undefined;
      status.show();
      await notifyAlerts(await c.alerts(20));
    } catch (e) {
      status.text = "$(shield) Spend Firewall: offline";
      status.tooltip = e instanceof Error ? e.message : String(e);
      status.show();
    }
  }

  async function notifyAlerts(alerts: Alert[]) {
    for (const a of alerts.slice().reverse()) {
      if (seenAlerts.has(a.id)) continue;
      seenAlerts.add(a.id);
      if (firstAlertPoll) continue; // don't replay history on startup
      const msg = `Spend Firewall: ${a.scope_id} ${a.threshold >= 100 ? "blocked at" : "reached"} ${a.threshold}% of '${a.policy}' (${money(a.spent_usd)} of ${money(a.limit_usd)})`;
      const pick = await (a.threshold >= 100 ? vscode.window.showErrorMessage : vscode.window.showWarningMessage)(msg, "Open Dashboard");
      if (pick) vscode.commands.executeCommand("spendfirewall.openDashboard");
    }
    firstAlertPoll = false;
  }

  let timer: NodeJS.Timeout | undefined;
  const schedule = () => {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, Math.max(3, cfg().get<number>("pollSeconds") ?? 10) * 1000);
  };
  schedule();
  ctx.subscriptions.push({ dispose: () => timer && clearInterval(timer) });
  ctx.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("spendfirewall")) {
        client = null;
        schedule();
        refresh();
      }
    }),
  );

  const reg = (id: string, fn: (...args: any[]) => unknown) => ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));

  reg("spendfirewall.signIn", async () => {
    const url = await vscode.window.showInputBox({
      prompt: "Gateway URL",
      value: cfg().get<string>("gatewayUrl"),
      ignoreFocusOut: true,
    });
    if (!url) return;
    const key = await vscode.window.showInputBox({ prompt: "Admin API key (sf-…)", password: true, ignoreFocusOut: true });
    if (!key) return;
    try {
      const me = await new AdminClient(url, key).me();
      await cfg().update("gatewayUrl", url, vscode.ConfigurationTarget.Global);
      await ctx.secrets.store(SECRET_KEY, key);
      client = null;
      vscode.window.showInformationMessage(`Spend Firewall: connected to "${me.tenant.name}"`);
      refresh();
    } catch (e) {
      vscode.window.showErrorMessage(`Spend Firewall: could not sign in: ${e instanceof Error ? e.message : e}`);
    }
  });

  reg("spendfirewall.signOut", async () => {
    await ctx.secrets.delete(SECRET_KEY);
    client = null;
    refresh();
  });

  reg("spendfirewall.refresh", refresh);

  reg("spendfirewall.killSession", async (n?: Node) => {
    const c = await getClient(ctx);
    if (!c || n?.kind !== "session") return;
    const ok = await vscode.window.showWarningMessage(
      `Kill session ${n.s.session_id}? Its next LLM call (and any live stream) will be blocked.`,
      { modal: true },
      "Kill",
    );
    if (ok !== "Kill") return;
    await c.kill("session", n.s.session_id, "killed from VS Code");
    refresh();
  });

  reg("spendfirewall.reviveSession", async (n?: Node) => {
    const c = await getClient(ctx);
    if (!c || n?.kind !== "session") return;
    await c.unkill("session", n.s.session_id);
    refresh();
  });

  reg("spendfirewall.openDashboard", () => vscode.env.openExternal(vscode.Uri.parse(cfg().get<string>("dashboardUrl")!)));

  reg("spendfirewall.connectWorkspace", async () => {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) return vscode.window.showErrorMessage("Open a folder first.");
    const c = await getClient(ctx);
    if (!c) return vscode.commands.executeCommand("spendfirewall.signIn");
    const agent = workspaceAgentId();
    const gw = cfg().get<string>("gatewayUrl")!.replace(/\/+$/, "");
    const envUri = vscode.Uri.joinPath(folder.uri, ".env");
    let original = "";
    try {
      original = new TextDecoder().decode(await vscode.workspace.fs.readFile(envUri));
    } catch {
      /* no .env yet */
    }
    const vars: Record<string, string> = {
      OPENAI_BASE_URL: `${gw}/v1`,
      SPENDFIREWALL_URL: gw,
      SPENDFIREWALL_AGENT_ID: agent,
    };
    if (!/^\s*SPENDFIREWALL_API_KEY\s*=/m.test(original)) {
      const k = await c.createKey(`vscode ${agent}`, "proxy");
      vars.SPENDFIREWALL_API_KEY = k.key;
      vars.OPENAI_API_KEY = k.key;
    }
    const { text, changed } = mergeEnv(original, vars);
    if (!changed.length) return vscode.window.showInformationMessage("Spend Firewall: .env already connected.");
    const go = await vscode.window.showInformationMessage(
      `Update .env (${changed.join(", ")})? LLM calls from this workspace will go through the firewall as agent "${agent}".`,
      { modal: true },
      "Update .env",
    );
    if (go !== "Update .env") return;
    await vscode.workspace.fs.writeFile(envUri, new TextEncoder().encode(text));
    await ensureGitignored(folder.uri);
    vscode.window.showInformationMessage(
      "Spend Firewall: .env updated. Add an X-Session-Id per run (the Python/JS SDKs do it for you).",
    );
    output.appendLine(`connected ${folder.name} as ${agent}: ${changed.join(", ")}`);
  });

  reg("spendfirewall.newPolicyFile", async () => {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) return;
    const uri = vscode.Uri.joinPath(folder.uri, "spendfirewall.yaml");
    try {
      await vscode.workspace.fs.stat(uri);
    } catch {
      await vscode.workspace.fs.writeFile(uri, new TextEncoder().encode(POLICY_TEMPLATE));
    }
    await vscode.window.showTextDocument(uri);
  });

  reg("spendfirewall.pushPolicy", async (uri?: vscode.Uri) => {
    const c = await getClient(ctx);
    if (!c) return vscode.commands.executeCommand("spendfirewall.signIn");
    const target = uri ?? vscode.window.activeTextEditor?.document.uri ?? (await findPolicyFile());
    if (!target) return vscode.window.showErrorMessage("No spendfirewall.yaml found. Run 'Spend Firewall: Create Policy File'.");
    const doc = await vscode.workspace.openTextDocument(target);
    let file: PolicyFile;
    try {
      file = (target.path.endsWith(".json") ? JSON.parse(doc.getText()) : parseYaml(doc.getText())) as PolicyFile;
    } catch (e) {
      return vscode.window.showErrorMessage(`Spend Firewall: can't parse ${target.path}: ${e}`);
    }
    const ok = await vscode.window.showWarningMessage(
      `Push ${file.budgets?.length ?? 0} budgets to ${cfg().get<string>("gatewayUrl")}? Enabled budgets not in the file will be disabled.`,
      { modal: true },
      "Push",
    );
    if (ok !== "Push") return;
    try {
      const r = await c.syncPolicies(file);
      vscode.window.showInformationMessage(`Spend Firewall: ${r.created} created, ${r.updated} updated, ${r.disabled} disabled.`);
    } catch (e) {
      vscode.window.showErrorMessage(`Spend Firewall: push failed: ${e instanceof Error ? e.message : e}`);
    }
  });

  refresh();
}

async function findPolicyFile(): Promise<vscode.Uri | undefined> {
  const found = await vscode.workspace.findFiles("**/spendfirewall.{yaml,yml,json}", "**/node_modules/**", 1);
  return found[0];
}

async function ensureGitignored(root: vscode.Uri) {
  const gi = vscode.Uri.joinPath(root, ".gitignore");
  let text = "";
  try {
    text = new TextDecoder().decode(await vscode.workspace.fs.readFile(gi));
  } catch {
    return; // not a git project we manage
  }
  if (!/^\.env$/m.test(text)) {
    await vscode.workspace.fs.writeFile(gi, new TextEncoder().encode(text.replace(/\n*$/, "\n") + ".env\n"));
  }
}

export function deactivate() {}
