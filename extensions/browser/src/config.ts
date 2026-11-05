import { AdminClient } from "spendfirewall";

export interface Config {
  gatewayUrl: string;
  adminKey: string;
  dashboardUrl: string;
}

export async function loadConfig(): Promise<Config | null> {
  const c = (await chrome.storage.local.get(["gatewayUrl", "adminKey", "dashboardUrl"])) as Partial<Config>;
  if (!c.gatewayUrl || !c.adminKey) return null;
  return { gatewayUrl: c.gatewayUrl, adminKey: c.adminKey, dashboardUrl: c.dashboardUrl || "http://localhost:5173" };
}

export async function saveConfig(c: Config | null): Promise<void> {
  if (c) await chrome.storage.local.set(c);
  else await chrome.storage.local.remove(["gatewayUrl", "adminKey", "dashboardUrl", "lastAlertId"]);
}

export const clientFor = (c: Config) => new AdminClient(c.gatewayUrl, c.adminKey);
