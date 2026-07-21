import type { MetadataRoute } from "next";

// Base URL for canonical/sitemap generation.
// Override at build time with NEXT_PUBLIC_SITE_URL for the real domain.
// Fallback matches metadataBase in app/layout.tsx.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://project-mri.dev";

// Every real, indexable route under app/. Keep in sync with components/nav.tsx.
const ROUTES = [
  "/",
  "/features",
  "/architecture",
  "/install",
  "/manifesto",
  "/roadmap",
  "/about",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return ROUTES.map((route) => ({
    url: new URL(route, SITE_URL).toString(),
    lastModified,
    changeFrequency: "monthly",
    priority: route === "/" ? 1 : 0.8,
  }));
}
