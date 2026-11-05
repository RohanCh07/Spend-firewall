import { test } from "node:test";
import assert from "node:assert/strict";
import { AdminClient, firewallHeaders, isFirewallBlock, openAIOptions } from "../dist/index.js";

test("headers", () => {
  assert.deepEqual(firewallHeaders({ agentId: "a", sessionId: "s" }), { "X-Agent-Id": "a", "X-Session-Id": "s" });
  const o = openAIOptions({ baseURL: "http://x/v1", apiKey: "k", agentId: "a" });
  assert.match(o.defaultHeaders["X-Session-Id"], /^s-[a-z0-9]{16}$/);
});

test("isFirewallBlock", () => {
  assert.ok(isFirewallBlock({ status: 402, error: { type: "budget_exceeded" } }));
  assert.ok(!isFirewallBlock({ status: 500, error: { type: "server_error" } }));
});

test("admin client builds requests", async () => {
  const calls = [];
  const fake = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } });
  };
  const c = new AdminClient("http://gw:8080/v1/", "sf-k", fake);
  await c.sessions({ hours: 1 });
  assert.equal(calls[0].url, "http://gw:8080/v1/admin/sessions?hours=1");
  assert.equal(calls[0].init.headers.authorization, "Bearer sf-k");
});

test("admin client surfaces firewall errors", async () => {
  const fake = async () => new Response(JSON.stringify({ error: { type: "forbidden", message: "no" } }), { status: 403 });
  await assert.rejects(new AdminClient("http://gw", "k", fake).me(), (e) => e.type === "forbidden" && e.status === 403);
});
