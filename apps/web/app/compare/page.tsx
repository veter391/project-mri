import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section, SectionHeader } from "@/components/ui/container";
import { Card } from "@/components/ui/card";
import { TerminalWindow } from "@/components/ui/terminal-window";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "MRI vs. Repowise and AI Code Scanners — Comparison",
  description:
    "An honest, sourced comparison: MRI reads real session logs and closes a decision-to-consequence loop that git-metadata guessers and paid SaaS scanners don't — MIT-forever, self-hostable.",
  alternates: { canonical: "/compare" },
};

type V = "yes" | "part" | "no";

const TOOLS = ["MRI", "Repowise", "Structure graphs", "Metrics tools"] as const;

const ROWS: {
  capability: string;
  cells: [
    { v: V; note: string },
    { v: V; note: string },
    { v: V; note: string },
    { v: V; note: string },
  ];
}[] = [
  {
    capability: "Session-log attribution (prompt → line)",
    cells: [
      { v: "yes", note: "reads ~/.claude, ~/.cursor" },
      { v: "no", note: "git-metadata only" },
      { v: "no", note: "out of scope" },
      { v: "no", note: "out of scope" },
    ],
  },
  {
    capability: "Authorship-decomposed risk",
    cells: [
      { v: "yes", note: "AI vs human share" },
      { v: "part", note: "from metadata" },
      { v: "no", note: "—" },
      { v: "no", note: "not by authorship" },
    ],
  },
  {
    capability: "Decision → consequence loop",
    cells: [
      { v: "yes", note: "correlational, guardrailed" },
      { v: "no", note: "none" },
      { v: "no", note: "none" },
      { v: "no", note: "none" },
    ],
  },
  {
    capability: "Git-history mining · hotspots",
    cells: [
      { v: "yes", note: "churn, ownership, bus factor" },
      { v: "yes", note: "core capability" },
      { v: "part", note: "some" },
      { v: "part", note: "some" },
    ],
  },
  {
    capability: "Explainable, decomposable scores",
    cells: [
      { v: "yes", note: "every number traces to source" },
      { v: "yes", note: "explainable scoring" },
      { v: "no", note: "structure only" },
      { v: "part", note: "metrics only" },
    ],
  },
  {
    capability: "MCP server (agent-native)",
    cells: [
      { v: "yes", note: "read-only, stdio" },
      { v: "part", note: "varies" },
      { v: "part", note: "some ship one" },
      { v: "no", note: "—" },
    ],
  },
  {
    capability: "License",
    cells: [
      { v: "yes", note: "MIT-forever" },
      { v: "part", note: "AGPL + paid" },
      { v: "part", note: "varies" },
      { v: "part", note: "varies" },
    ],
  },
  {
    capability: "Self-hostable · zero telemetry",
    cells: [
      { v: "yes", note: "egress-tested" },
      { v: "part", note: "core only" },
      { v: "part", note: "varies" },
      { v: "part", note: "varies" },
    ],
  },
];

const MARK: Record<V, { glyph: string; label: string; className: string }> = {
  yes: { glyph: "✓", label: "yes", className: "text-risk-low" },
  part: { glyph: "~", label: "partial", className: "text-risk-medium" },
  no: { glyph: "✕", label: "no", className: "text-risk-critical" },
};

const DIFFERENTIATORS = [
  {
    title: "Session-log provenance",
    body: "Metadata tells you a commit looks AI-authored. Session logs tell you which prompt produced which lines. That is a strictly richer signal a metadata heuristic cannot reconstruct.",
  },
  {
    title: "The decision → consequence loop",
    body: "Link a decision to the metric that moved later — as correlation, never causation, with confounder guardrails. No free tool, and to our knowledge no paid one, closes this loop end-to-end.",
  },
  {
    title: "Trust as structure, not marketing",
    body: "MIT-forever, zero-telemetry, fully self-hostable. A tool that reads your prompts and your source has to be inspectable and un-revocable to be adopted — so it is.",
  },
];

export default function ComparePage() {
  return (
    <>
      <PageHeader
        eyebrow="how it compares"
        title="An honest look at the neighborhood."
        lede="MRI is not the only tool that mines git history or ships an MCP. This page states, cell by cell, where a peer does something MRI doesn't — and where the differences are real. Every claim here is one we can defend."
      />

      <Section>
        <Container>
          <SectionHeader
            eyebrow="the honest framing"
            title="Individually, most capabilities have a rival."
            lede="The closest peer is Repowise (AGPL + paid). The white space is narrow and specific: session-log prompt-level attribution fused with risk decomposition, a decision-to-consequence loop, and a genuinely permissive MIT-forever license. MRI competes on completeness and trust — not on a claim that no one else is in this space."
          />

          <TerminalWindow
            title="neighborhood.csv"
            meta="last verified 2026-07"
            tone="surface"
            bodyClassName="p-0"
            className="mt-8"
          >
          <div className="overflow-x-auto p-5">
            <table className="w-full min-w-[720px] border-collapse text-left">
              <caption className="sr-only">
                Capability comparison of MRI, Repowise, structure-graph tools, and
                metrics tools
              </caption>
              <thead>
                <tr className="border-hairline border-b">
                  <th
                    scope="col"
                    className="text-mute py-3 pr-4 font-sans text-body-sm font-semibold"
                  >
                    Capability
                  </th>
                  {TOOLS.map((t, i) => (
                    <th
                      key={t}
                      scope="col"
                      className={`px-3 py-3 font-sans text-body-sm font-semibold ${i === 0 ? "text-accent" : "text-primary"}`}
                    >
                      {t}
                      {i >= 2 && <span className="text-mute">*</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.capability} className="border-hairline border-b">
                    <th
                      scope="row"
                      className="text-secondary py-3 pr-4 align-top font-body text-body-sm font-normal"
                    >
                      {row.capability}
                    </th>
                    {row.cells.map((cell, i) => {
                      const m = MARK[cell.v];
                      return (
                        <td key={i} className="px-3 py-3 align-top">
                          <span className={`mr-1.5 font-mono font-semibold ${m.className}`}>
                            <span aria-hidden="true">{m.glyph}</span>
                            <span className="sr-only">{m.label}: </span>
                          </span>
                          <span className="text-mute font-mono text-mono-sm">
                            {cell.note}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </TerminalWindow>
          <p className="text-mute mt-3 font-mono text-mono-sm">
            <span className="text-risk-low">✓</span> yes ·{" "}
            <span className="text-risk-medium">~</span> partial ·{" "}
            <span className="text-risk-critical">✕</span> no. * Structure-graph and
            metrics tools are categories, not single products. Peer capabilities
            as understood from public sources · last verified 2026-07 · corrections
            welcome via a GitHub issue.
          </p>
        </Container>
      </Section>

      <Section>
        <Container>
          <SectionHeader
            eyebrow="where MRI is genuinely different"
            title="Three differences that are real."
          />
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {DIFFERENTIATORS.map((d) => (
              <Card key={d.title}>
                <h3 className="text-accent font-sans text-body font-semibold">
                  {d.title}
                </h3>
                <p className="text-secondary mt-2 font-body text-body-sm leading-relaxed">
                  {d.body}
                </p>
              </Card>
            ))}
          </div>
        </Container>
      </Section>

      <Section>
        <Container narrow>
          <Card className="bg-raised md:p-9">
            <h2 className="text-[length:var(--text-h3)] font-semibold text-balance">
              The honest 5/5 is a systems claim, not a feature claim.
            </h2>
            <p className="text-secondary mt-4 font-body text-body-lg leading-relaxed">
              Every rival owns a segment of the loop. Repowise owns
              attribution + risk — from metadata, closed and paid, with no
              consequence. Structure tools own the graph. None of them owns the
              whole loop, and none is simultaneously free, self-hostable,
              explainable, and MIT-forever. Completeness under those four
              constraints is the difference — and it survives fact-checking of
              every individual claim.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <ButtonLink href={SITE.github}>
                Audit the claims
                <ArrowUpRightIcon width={16} height={16} />
              </ButtonLink>
              <ButtonLink href="/how-it-works" variant="secondary">
                How it works
              </ButtonLink>
            </div>
          </Card>
        </Container>
      </Section>
    </>
  );
}
