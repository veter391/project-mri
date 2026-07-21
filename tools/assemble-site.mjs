// Assemble the static marketing site into ./_site for a Cloudflare Workers
// static-assets deploy. Run AFTER `tsc` (which compiles ts/ -> dist/).
//
// The repo root holds far more than the site (backend, src, docs, …), so we
// copy an explicit allow-list — never the whole tree — into a clean output dir.
//
//   node tools/assemble-site.mjs   (or: pnpm run site:bundle)

import { cp, mkdir, rm, readdir, access } from "node:fs/promises";
import { constants } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "_site");

// Top-level HTML pages (each is a real route; SPA-nav enhances them at runtime).
const PAGES = [
  "index.html",
  "features.html",
  "comparison.html",
  "architecture.html",
  "install.html",
  "self-host.html",
  "docs.html",
  "manifesto.html",
  "roadmap.html",
  "about.html",
];

// Directories copied verbatim.
const DIRS = ["css", "dist", "data", "demo"];

// Loose files copied when present.
const FILES = ["robots.txt", "sitemap.xml"];

async function exists(p) {
  try {
    await access(p, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  // dist/ must exist — tsc has to run first.
  const distJs = join(ROOT, "dist", "index.js");
  if (!(await exists(distJs))) {
    console.error("error: dist/index.js missing — run `tsc` (pnpm run build:site) before assembling.");
    process.exit(1);
  }

  await rm(OUT, { recursive: true, force: true });
  await mkdir(OUT, { recursive: true });

  let copied = 0;

  for (const page of PAGES) {
    const src = join(ROOT, page);
    if (await exists(src)) {
      await cp(src, join(OUT, page));
      copied++;
    } else {
      console.warn(`warn: page missing, skipped: ${page}`);
    }
  }

  for (const dir of DIRS) {
    const src = join(ROOT, dir);
    if (await exists(src)) {
      // dist/ also holds Python build artifacts (wheels/tarballs) — copy only JS + maps.
      if (dir === "dist") {
        await mkdir(join(OUT, "dist"), { recursive: true });
        for (const entry of await readdir(src)) {
          if (entry.endsWith(".js") || entry.endsWith(".js.map")) {
            await cp(join(src, entry), join(OUT, "dist", entry));
            copied++;
          }
        }
      } else {
        await cp(src, join(OUT, dir), { recursive: true });
        copied++;
      }
    } else {
      console.warn(`warn: dir missing, skipped: ${dir}`);
    }
  }

  for (const file of FILES) {
    const src = join(ROOT, file);
    if (await exists(src)) {
      await cp(src, join(OUT, file));
      copied++;
    }
  }

  console.log(`assembled _site/ (${copied} items) — ready for wrangler deploy`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
