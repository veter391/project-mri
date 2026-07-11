import type { NextConfig } from "next";

// Static export: `next build` emits a flat `out/` (no Node runtime). It is
// embedded into the Python package and served by FastAPI under /dashboard,
// so the operator installs `project-mri` and runs `mri serve` — Python only.
const nextConfig: NextConfig = {
  output: "export",
  basePath: "/dashboard",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
