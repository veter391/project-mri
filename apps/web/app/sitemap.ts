import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";

const ROUTES = [
  "",
  "/how-it-works",
  "/compare",
  "/demo",
  "/manifesto",
  "/about",
  "/contributing",
  "/changelog",
  "/docs",
  "/docs/quickstart",
  "/docs/cli",
  "/docs/mcp",
  "/docs/self-hosting",
  "/docs/ci",
  "/docs/session-log-setup",
  "/docs/architecture",
];

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((path) => ({
    url: `${SITE.url}${path}`,
    changeFrequency: path === "" ? "weekly" : "monthly",
    priority: path === "" ? 1 : path.startsWith("/docs") ? 0.6 : 0.8,
  }));
}
