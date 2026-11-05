# Spend Firewall for VS Code

See and stop what your AI agents spend while you build them.

- **Status bar:** this workspace's agent spend today, turns yellow when a live session is being blocked.
- **Sessions view:** live sessions with spend, calls, blocks and budget %; expand for every call. **Kill** or **Revive** a session inline.
- **Connect Workspace:** writes `OPENAI_BASE_URL`, a new proxy key and `SPENDFIREWALL_AGENT_ID` into `.env` (and makes sure `.env` is git-ignored), so local runs go through the firewall.
- **Policy files:** `spendfirewall.yaml` gets autocomplete and validation (needs the Red Hat YAML extension; `spendfirewall.json` works out of the box). **Push Policy File** applies it to the gateway.
- **Alerts:** a notification when a budget hits 50 / 80 / 100%.

## Commands

`Spend Firewall: Sign In`, `Connect Workspace (.env)`, `Create Policy File`, `Push Policy File`, `Open Dashboard`, `Refresh`, `Sign Out`.

## Develop

```bash
pnpm install && pnpm --filter spendfirewall build
cd extensions/vscode && pnpm build
# F5 in VS Code with this folder open, or:
pnpm package   # -> spendfirewall-vscode-0.1.0.vsix
```
