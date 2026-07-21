// Canonical site constants — single source of truth for the marketing site.
// Values reconciled against the repo docs (BUILD-NOTES / _workspace/docs-working).
// GitHub org form is canonical; veter391/* is the owner's personal remote.

export const SITE = {
  name: "MRI",
  pkg: "project-mri",
  url: "https://project-mri.dev",
  github: "https://github.com/project-mri/project-mri",
  license: "https://github.com/project-mri/project-mri/blob/main/LICENSE",
  version: "0.3.0",
  port: 7331,
  tagline: "MRI reads what's actually in your codebase — and who actually wrote it.",
  description:
    "MRI decomposes AI-authored vs human-authored risk from real session logs, tracks decisions to measured outcomes, and stays MIT-licensed and self-hostable forever.",
} as const;

export type NavLink = { href: string; label: string };

// Primary navigation (DEMO-SITE-SPEC §3). GitHub is a distinct icon item, kept
// out of this list so it never gets buried in the mobile drawer's text links.
export const NAV_LINKS: readonly NavLink[] = [
  { href: "/how-it-works", label: "How It Works" },
  { href: "/compare", label: "Compare" },
  { href: "/docs", label: "Docs" },
  { href: "/demo", label: "Demo" },
  { href: "/manifesto", label: "Manifesto" },
] as const;

export const FOOTER_COLUMNS: readonly {
  title: string;
  links: readonly NavLink[];
}[] = [
  {
    title: "Product",
    links: [
      { href: "/how-it-works", label: "How It Works" },
      { href: "/compare", label: "Compare" },
      { href: "/demo", label: "Demo" },
      { href: "/changelog", label: "Changelog" },
    ],
  },
  {
    title: "Docs",
    links: [
      { href: "/docs/quickstart", label: "Quickstart" },
      { href: "/docs/cli", label: "CLI reference" },
      { href: "/docs/mcp", label: "MCP server" },
      { href: "/docs/self-hosting", label: "Self-hosting" },
    ],
  },
  {
    title: "Project",
    links: [
      { href: "/manifesto", label: "Manifesto" },
      { href: "/about", label: "About" },
      { href: "/contributing", label: "Contributing" },
      { href: SITE.github, label: "GitHub" },
    ],
  },
] as const;
