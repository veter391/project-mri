import { Link } from "@/components/link";
import { SITE, FOOTER_COLUMNS } from "@/lib/site";
import { Logo } from "@/components/logo";
import { GitHubIcon, ArrowUpRightIcon } from "@/components/icons";

function isExternal(href: string) {
  return href.startsWith("http");
}

export function Footer() {
  return (
    <footer
      id="site-footer"
      className="border-hairline mt-24 border-t"
    >
      <div className="mx-auto max-w-[var(--container-content)] px-4 py-14 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div className="max-w-xs">
            <Logo />
            <p className="text-secondary mt-4 font-body text-body-sm leading-relaxed">
              Local-first codebase intelligence. Explainable risk, real AI
              provenance, zero telemetry.
            </p>
            <p className="text-mute mt-4 font-mono text-mono-sm">
              Local-first. MIT-forever.
            </p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h2 className="text-mute font-sans text-caption font-medium tracking-[0.04em] uppercase">
                {col.title}
              </h2>
              <ul className="mt-4 flex flex-col gap-2.5">
                {col.links.map((l) =>
                  isExternal(l.href) ? (
                    <li key={l.href}>
                      <a
                        href={l.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-secondary hover:text-primary inline-flex items-center gap-1 font-body text-body-sm transition-colors"
                      >
                        {l.label}
                        <ArrowUpRightIcon width={13} height={13} />
                      </a>
                    </li>
                  ) : (
                    <li key={l.href}>
                      <Link
                        href={l.href}
                        className="text-secondary hover:text-primary font-body text-body-sm transition-colors"
                      >
                        {l.label}
                      </Link>
                    </li>
                  ),
                )}
              </ul>
            </nav>
          ))}
        </div>

        <div className="border-hairline mt-12 flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-mute font-mono text-mono-sm">
            © {SITE.version} · project-mri contributors · MIT
          </p>
          <div className="flex items-center gap-4">
            <span className="text-mute font-mono text-mono-sm">
              Facts over magic scores.
            </span>
            <a
              href={SITE.github}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="MRI on GitHub"
              className="text-secondary hover:text-primary transition-colors"
            >
              <GitHubIcon width={18} height={18} />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
