import type { NextConfig } from "next";

/**
 * Static export for a pure-static marketing site.
 *
 * `output: "export"` emits a fully static `out/` directory — no server runtime,
 * so it deploys to Cloudflare Workers static assets with the smallest possible
 * attack surface and the best Core Web Vitals. All interactivity is client-side
 * (Client Components hydrate in the browser); there is no SSR/ISR.
 *
 * - `images.unoptimized` — the Next image optimizer needs a server; on a static
 *   host we ship pre-sized assets and let the browser do the rest.
 * - `trailingSlash` — export writes `route/index.html`; trailing slashes keep
 *   relative asset URLs and Cloudflare's clean-URL handling in agreement.
 *
 * Security headers are NOT set here (headers() is a no-op under export); they
 * live in `public/_headers`, which Cloudflare applies to every response.
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
