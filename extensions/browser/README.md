# Spend Firewall browser extension

Manifest V3, works in Chrome, Edge and Firefox 121+.

- **Toolbar badge:** today's spend (e.g. `$1.8`), red when calls were blocked in the last hour, `!` when the gateway is unreachable.
- **Popup:** 24h spend / calls / blocked, live sessions with **Kill** / **Revive**, link to the dashboard.
- **Notifications:** desktop alert when a budget hits 50 / 80 / 100%; click to open the dashboard.

It's a companion, not an interceptor: agents run on servers, so the extension
reads and controls the gateway through its admin API. It only asks for host
access to the gateway's own origin, at sign-in.

```bash
pnpm install && pnpm --filter spendfirewall build
cd extensions/browser && pnpm build
# Chrome: chrome://extensions -> Developer mode -> Load unpacked -> extensions/browser/dist
# Firefox: about:debugging -> This Firefox -> Load Temporary Add-on -> dist/manifest.json
pnpm zip   # store upload
```
