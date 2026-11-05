import * as esbuild from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

mkdirSync("schema", { recursive: true });
cpSync("../../shared/policy-schema/policy.schema.json", "schema/policy.schema.json");

const opts = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "dist/extension.js",
  platform: "node",
  format: "cjs",
  target: "node18",
  external: ["vscode"],
  sourcemap: true,
};
const outs = [opts, { ...opts, entryPoints: ["src/envfile.ts"], outfile: "dist/envfile.mjs", format: "esm", sourcemap: false }];
if (process.argv.includes("--watch")) {
  for (const o of outs) await (await esbuild.context(o)).watch();
} else {
  for (const o of outs) await esbuild.build(o);
}
