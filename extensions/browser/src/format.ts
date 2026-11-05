/** Pure helpers shared by the popup and background worker (unit-tested). */

/** Compact money for a 4-character toolbar badge. */
export function badgeText(usd: number): string {
  if (usd <= 0) return "$0";
  if (usd < 0.01) return "<1¢";
  if (usd < 1) return `${Math.round(usd * 100)}¢`;
  if (usd < 10) return `$${usd.toFixed(1)}`;
  if (usd < 1000) return `$${Math.round(usd)}`;
  if (usd < 10000) return `$${(usd / 1000).toFixed(1)}k`;
  return `$${Math.round(usd / 1000)}k`;
}

export function money(v: number): string {
  return v >= 1 ? `$${v.toFixed(2)}` : v >= 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(5)}`;
}

export function originPattern(gatewayUrl: string): string {
  const u = new URL(gatewayUrl);
  return `${u.protocol}//${u.hostname}/*`;
}

export function ago(iso: string, now = Date.now()): string {
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z").getTime();
  const s = Math.max(0, (now - t) / 1000);
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
