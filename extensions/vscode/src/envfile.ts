/**
 * Merge variables into the text of a .env file, keeping comments, order and
 * unrelated lines. Pure function so it can be tested without VS Code.
 */
export function mergeEnv(original: string, vars: Record<string, string>): { text: string; changed: string[] } {
  const lines = original.length ? original.split(/\r?\n/) : [];
  const pending = new Map(Object.entries(vars));
  const changed: string[] = [];
  const out = lines.map((line) => {
    const m = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$/.exec(line);
    if (!m || !pending.has(m[1])) return line;
    const key = m[1];
    const value = pending.get(key)!;
    pending.delete(key);
    const current = m[2].trim().replace(/^["']|["']$/g, "");
    if (current === value) return line;
    changed.push(key);
    return `${key}=${quote(value)}`;
  });
  if (pending.size) {
    while (out.length && out[out.length - 1] === "") out.pop();
    if (out.length) out.push("");
    out.push("# Spend Firewall: route LLM calls through the gateway");
    for (const [k, v] of pending) {
      out.push(`${k}=${quote(v)}`);
      changed.push(k);
    }
  }
  return { text: out.join("\n").replace(/\n*$/, "\n"), changed };
}

function quote(v: string): string {
  return /[\s#"']/.test(v) ? JSON.stringify(v) : v;
}

export function defaultAgentId(folderName: string): string {
  const slug = folderName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "workspace";
  return `${slug}-dev`;
}
