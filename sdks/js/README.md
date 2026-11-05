# spendfirewall (JS/TS)

```ts
import OpenAI from "openai";
import { openAIOptions, isFirewallBlock, AdminClient } from "spendfirewall";

const client = new OpenAI(openAIOptions({ baseURL: "http://localhost:8080/v1", apiKey: process.env.SF_KEY!, agentId: "planner" }));
try {
  await client.chat.completions.create({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] });
} catch (e) {
  if (isFirewallBlock(e)) process.exit(1); // budget hit, loop or kill switch: stop, don't retry
  throw e;
}

const admin = new AdminClient("http://localhost:8080", process.env.SF_ADMIN_KEY!);
await admin.kill("session", "s-123", "runaway");
```

The dashboard and both extensions use `AdminClient` from this package.
