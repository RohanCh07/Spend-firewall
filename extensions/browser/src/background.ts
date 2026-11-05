/**
 * Background worker: every minute, update the toolbar badge with today's
 * spend and raise a desktop notification for new budget alerts.
 */
import { clientFor, loadConfig } from "./config";
import { badgeText, money } from "./format";

const ALARM = "spendfirewall.poll";

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM, { periodInMinutes: 1 });
  poll();
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(ALARM, { periodInMinutes: 1 });
  poll();
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === ALARM) poll();
});
chrome.runtime.onMessage.addListener((msg) => {
  if (msg === "poll") poll();
});
chrome.notifications.onClicked.addListener(async () => {
  const c = await loadConfig();
  if (c) chrome.tabs.create({ url: `${c.dashboardUrl}#activity` });
});

async function poll(): Promise<void> {
  const cfg = await loadConfig();
  if (!cfg) {
    await chrome.action.setBadgeText({ text: "" });
    await chrome.action.setTitle({ title: "Spend Firewall: click to connect" });
    return;
  }
  const api = clientFor(cfg);
  try {
    const sum = await api.summary(24);
    const recentBlocks = sum.timeseries.slice(-1)[0]?.blocked ?? 0;
    await chrome.action.setBadgeText({ text: badgeText(sum.total_cost_usd) });
    await chrome.action.setBadgeBackgroundColor({ color: recentBlocks > 0 ? "#dc2626" : "#e4572e" });
    await chrome.action.setTitle({
      title: `Spend Firewall\n${money(sum.total_cost_usd)} in 24h · ${sum.calls} calls · ${sum.blocked} blocked`,
    });
    await notifyNewAlerts(api);
  } catch (e) {
    await chrome.action.setBadgeText({ text: "!" });
    await chrome.action.setBadgeBackgroundColor({ color: "#6b7280" });
    await chrome.action.setTitle({ title: `Spend Firewall: ${e instanceof Error ? e.message : "offline"}` });
  }
}

async function notifyNewAlerts(api: ReturnType<typeof clientFor>): Promise<void> {
  const alerts = await api.alerts(20);
  const { lastAlertId } = (await chrome.storage.local.get("lastAlertId")) as { lastAlertId?: number };
  const newest = alerts[0]?.id ?? 0;
  if (lastAlertId === undefined) {
    // First run: remember where we are, don't replay history.
    await chrome.storage.local.set({ lastAlertId: newest });
    return;
  }
  const fresh = alerts.filter((a) => a.id > lastAlertId).reverse();
  for (const a of fresh) {
    const blocked = a.threshold >= 100;
    chrome.notifications.create(`alert-${a.id}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: blocked ? `Blocked: ${a.policy ?? "budget"}` : `${a.threshold}% of ${a.policy ?? "budget"}`,
      message: `${a.scope_id ?? ""}: ${money(a.spent_usd)} of ${money(a.limit_usd)}`,
      priority: blocked ? 2 : 0,
    });
  }
  if (newest > lastAlertId) await chrome.storage.local.set({ lastAlertId: newest });
}
