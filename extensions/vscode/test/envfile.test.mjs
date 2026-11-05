import { test } from "node:test";
import assert from "node:assert/strict";
import { defaultAgentId, mergeEnv } from "../dist/envfile.mjs";

test("appends missing vars under a header", () => {
  const { text, changed } = mergeEnv("FOO=1\n", { OPENAI_BASE_URL: "http://gw/v1" });
  assert.equal(text, "FOO=1\n\n# Spend Firewall: route LLM calls through the gateway\nOPENAI_BASE_URL=http://gw/v1\n");
  assert.deepEqual(changed, ["OPENAI_BASE_URL"]);
});

test("replaces existing values in place and keeps comments", () => {
  const src = "# keys\nexport OPENAI_BASE_URL=https://api.openai.com/v1\nOTHER=x\n";
  const { text, changed } = mergeEnv(src, { OPENAI_BASE_URL: "http://gw/v1" });
  assert.equal(text, "# keys\nOPENAI_BASE_URL=http://gw/v1\nOTHER=x\n");
  assert.deepEqual(changed, ["OPENAI_BASE_URL"]);
});

test("no-op when already set", () => {
  assert.deepEqual(mergeEnv('A="v"\n', { A: "v" }).changed, []);
});

test("agent id slug", () => {
  assert.equal(defaultAgentId("My Cool_Project"), "my-cool-project-dev");
});
