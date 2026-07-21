import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Changelog",
  description:
    "MRI release history. GitHub releases are the single source of truth; this page renders the summary and links to each tagged release.",
  alternates: { canonical: "/changelog" },
};

const RELEASES = [
  {
    version: "0.3.0",
    date: "2025-12-20",
    notes: [
      "Fusion moat end-to-end: session-log provenance, authorship-decomposed risk, decision → consequence loop.",
      "MCP server (stdio) exposing a read-only tool surface to agents.",
      "SARIF export with authorship properties for CI gating.",
    ],
  },
  {
    version: "0.2.0",
    date: "2025-12-19",
    notes: [
      "Six analyzers with per-contributor score ledgers.",
      "Self-contained HTML reports; remote clone-and-scan with token auth.",
    ],
  },
  {
    version: "0.1.0",
    date: "2025-12-18",
    notes: ["First public cut: CLI, git-history and structure analysis, local dashboard."],
  },
] as const;

export default function ChangelogPage() {
  return (
    <>
      <PageHeader
        eyebrow="changelog"
        title="Release history."
        lede="GitHub releases are the single source of truth. This page renders the summary — follow any version for the full, tagged notes."
      />
      <Section>
        <Container narrow>
          <ol className="flex flex-col">
            {RELEASES.map((r) => (
              <li
                key={r.version}
                className="border-hairline flex flex-col gap-3 border-b py-8 first:pt-0 sm:flex-row sm:gap-8"
              >
                <div className="sm:w-40 sm:shrink-0">
                  <span className="text-accent font-mono text-mono-lg font-semibold">
                    v{r.version}
                  </span>
                  <p className="text-mute mt-1 font-mono text-mono-sm">{r.date}</p>
                </div>
                <ul className="flex flex-col gap-2">
                  {r.notes.map((n) => (
                    <li
                      key={n}
                      className="text-secondary flex gap-2 font-body text-body leading-relaxed"
                    >
                      <span className="text-accent mt-1 font-mono text-mono-sm">→</span>
                      {n}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/releases`} variant="secondary">
              All releases on GitHub
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
