import * as esbuild from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

mkdirSync("dist", { recursive: true });
cpSync("static", "dist", { recursive: true });
cpSync("icons", "dist/icons", { recursive: true });

const common = { bundle: true, format: "esm", target: "chrome110", sourcemap: false };
const builds = [
  { ...common, entryPoints: ["src/background.ts"], outfile: "dist/background.js" },
  { ...common, entryPoints: ["src/popup.ts"], outfile: "dist/popup.js" },
  { ...common, entryPoints: ["src/format.ts"], outfile: "dist/format.mjs", platform: "neutral" },
];
if (process.argv.includes("--watch")) for (const b of builds) await (await esbuild.context(b)).watch();
else for (const b of builds) await esbuild.build(b);
