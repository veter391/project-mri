// Copy the static Next export into the Python package so `pip install project-mri`
// ships the dashboard and `mri serve` can serve it with no Node runtime.
//
// Also emit a CSP manifest: Next's App Router bootstraps through inline
// <script> tags, which the API's `script-src 'self'` policy blocks outright.
// Rather than weakening the policy with 'unsafe-inline', we hash every inline
// script at build time and let the server allow exactly those hashes.
import { createHash } from "node:crypto";
import { cpSync, existsSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
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

function htmlFiles(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return htmlFiles(full);
    return full.endsWith(".html") ? [full] : [];
  });
}

// Inline scripts only — anything with a src= attribute is covered by 'self'.
const INLINE_SCRIPT = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
const hashes = new Set();
for (const file of htmlFiles(dest)) {
  const html = readFileSync(file, "utf8");
  for (const [, body] of html.matchAll(INLINE_SCRIPT)) {
    if (!body) continue;
    hashes.add("sha256-" + createHash("sha256").update(body, "utf8").digest("base64"));
  }
}

const manifest = join(dest, "csp-script-hashes.json");
writeFileSync(manifest, JSON.stringify([...hashes], null, 2) + "\n", "utf8");

console.log(`embed: ${out} -> ${dest}`);
console.log(`embed: ${hashes.size} inline-script hashes -> ${manifest}`);
