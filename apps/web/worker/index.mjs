// Thin Cloudflare Worker in front of the static assets: serves ./out via the
// ASSETS binding and attaches security headers programmatically. Exists because
// Cloudflare's _headers file caps each line at 2000 chars — our strict CSP
// (per-build inline-script hashes, no unsafe-inline) is longer than that.
// CSP + headers are generated at build time into ./csp.mjs by tools/gen-headers.mjs.

import { CSP, SECURITY_HEADERS } from "./csp.mjs";

export default {
  async fetch(request, env) {
    const res = await env.ASSETS.fetch(request);
    const headers = new Headers(res.headers);

    headers.set("Content-Security-Policy", CSP);
    for (const [k, v] of Object.entries(SECURITY_HEADERS)) headers.set(k, v);

    const { pathname } = new URL(request.url);
    if (pathname.startsWith("/_next/static/")) {
      // Content-hashed build assets — safe to cache forever.
      headers.set("Cache-Control", "public, max-age=31536000, immutable");
    }

    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers,
    });
  },
};
