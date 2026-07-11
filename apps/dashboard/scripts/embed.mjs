// Copy the static Next export into the Python package so `pip install project-mri`
// ships the dashboard and `mri serve` can serve it with no Node runtime.
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "..", "out");
const dest = resolve(here, "..", "..", "..", "src", "mri", "_frontend", "dashboard");

if (!existsSync(out)) {
  console.error(`embed: build output not found at ${out} — run "next build" first`);
  process.exit(1);
}
if (existsSync(dest)) rmSync(dest, { recursive: true, force: true });
cpSync(out, dest, { recursive: true });
console.log(`embed: ${out} -> ${dest}`);
