import { test } from "node:test";
import assert from "node:assert/strict";
import { ago, badgeText, originPattern } from "../dist/format.mjs";

test("badge fits in 4 chars", () => {
  assert.equal(badgeText(0), "$0");
  assert.equal(badgeText(0.004), "<1¢");
  assert.equal(badgeText(0.42), "42¢");
  assert.equal(badgeText(3.456), "$3.5");
  assert.equal(badgeText(123), "$123");
  assert.equal(badgeText(4500), "$4.5k");
  for (const v of [0, 0.004, 0.42, 3.4, 99, 999, 4500, 99999]) assert.ok(badgeText(v).length <= 5, badgeText(v));
});

test("origin pattern for permission request", () => {
  assert.equal(originPattern("http://localhost:8080/v1"), "http://localhost/*");
  assert.equal(originPattern("https://fw.example.com"), "https://fw.example.com/*");
});

test("ago", () => {
  assert.equal(ago("2026-01-01T00:00:00Z", Date.parse("2026-01-01T00:05:00Z")), "5m");
  assert.equal(ago("2026-01-01T00:00:00", Date.parse("2026-01-01T02:00:00Z")), "2h");
});
