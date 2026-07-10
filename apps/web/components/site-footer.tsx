import Link from "next/link";

const GITHUB = "https://github.com/veter391/project-mri";

const COLUMNS = [
  {
    title: "Project",
    links: [
      { href: "/features", label: "Features" },
      { href: "/architecture", label: "Architecture" },
      { href: "/roadmap", label: "Roadmap" },
      { href: "/manifesto", label: "Manifesto" },
    ],
  },
  {
    title: "Get started",
    links: [
      { href: "/install", label: "Install" },
      { href: GITHUB, label: "GitHub ↗", external: true },
      { href: "/about", label: "About" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto grid max-w-5xl gap-8 px-6 py-12 sm:grid-cols-[1.5fr_1fr_1fr]">
        <div>
          <div className="mb-2 font-bold text-accent">project-mri</div>
          <p className="max-w-xs text-[13px] leading-relaxed text-secondary">
            An MRI for your codebase. Local-first, explainable, open source.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <h4 className="mb-3 text-xs tracking-widest text-mute">{col.title}</h4>
            <ul className="space-y-2 text-sm">
              {col.links.map((l) =>
                "external" in l && l.external ? (
                  <li key={l.href}>
                    <a href={l.href} className="text-secondary hover:text-accent">
                      {l.label}
                    </a>
                  </li>
                ) : (
                  <li key={l.href}>
                    <Link href={l.href} className="text-secondary hover:text-accent">
                      {l.label}
                    </Link>
                  </li>
                ),
              )}
            </ul>
          </div>
        ))}
      </div>
      <div className="mx-auto flex max-w-5xl flex-col gap-2 border-t border-line px-6 py-6 text-[11px] text-mute sm:flex-row sm:items-center sm:justify-between">
        <span>project-mri · facts over magic scores</span>
        <span>MIT · your code never leaves your machine</span>
      </div>
    </footer>
  );
}
