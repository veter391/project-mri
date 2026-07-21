import type { MetadataRoute } from "next";

// Override at build time with NEXT_PUBLIC_SITE_URL for the real domain.
// Fallback matches metadataBase in app/layout.tsx.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://project-mri.dev";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: new URL("/sitemap.xml", SITE_URL).toString(),
    host: SITE_URL,
  };
}
