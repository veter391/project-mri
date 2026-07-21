import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { TerminalWindow } from "@/components/ui/terminal-window";
import { AuthorshipSplitBar } from "@/components/viz/authorship-split-bar";
import { DecisionConsequenceStrip } from "@/components/viz/decision-consequence-strip";
import { SITE } from "@/lib/site";
import { ArrowRightIcon } from "@/components/icons";
import { Watermark } from "@/components/ui/watermark";
import { cn } from "@/lib/cn";

export const metadata: Metadata = {
  title: "How MRI Works — Session Logs, Risk Scoring & Consequence Tracking",
  description:
    "Five stages, each with the real module that does it and the open source it builds on: git history + AST, session-log provenance, authorship-decomposed risk, decisions, consequences.",
  alternates: { canonical: "/how-it-works" },
};

/* Each stage ships its own visual artifact — no two sections look alike. */

function StageShell({
  n,
  title,
  module,
  body,
  oss,
  artifact,
  flip = false,
}: {
  n: string;
  title: string;
  module: string;
  body: React.ReactNode;
  oss?: string[];
  artifact: React.ReactNode;
  flip?: boolean;
}) {
  return (
    <section className="border-hairline relative border-t py-12 md:py-16">
      {/* watermark numeral */}
      <Watermark text={n} className="-top-8 right-0 h-28 md:h-40" />
      <div className="grid items-center gap-8 lg:grid-cols-12 lg:gap-12">
        <div className={cn("min-w-0 lg:col-span-5", flip && "lg:order-2")}>
          <p className="font-mono text-mono-sm">
            <span className="text-accent">{n}</span>
            <span className="text-mute"> / 05</span>
          </p>
          <h2 className="mt-3 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
            {title}
          </h2>
          <p className="text-mute mt-2 font-mono text-mono-sm break-words">{module}</p>
          <p className="text-secondary mt-4 font-body text-body-lg leading-relaxed text-pretty">
            {body}
          </p>
          {oss && oss.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              {oss.map((o) => (
                <Badge key={o} tone="neutral">
                  {o}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className={cn("min-w-0 lg:col-span-7", flip && "lg:order-1")}>
          {artifact}
        </div>
      </div>
    </section>
  );
}

const mono = "font-mono text-mono-sm leading-relaxed";

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader
        eyebrow="how it works"
        title="Convinced by the mechanism, not the marketing."
        lede="Five stages. Real module paths, real open source, real output — every claim below is one you can go check."
      />

      <Section className="pt-4 md:pt-6">
        <Container>
          {/* 01 — history + structure: scan log artifact */}
          <StageShell
            n="01"
            title="History + structure"
            module="backend/mri/analyzers/git_history.py · architecture.py"
            body={
              <>
                First, an image of what&apos;s actually there. MRI walks the full
                commit history and parses a real AST — hotspots, churn,
                ownership, coupling and complexity all come from measurements,
                not diff-shape guesses.
              </>
            }
            oss={["PyDriller", "py-tree-sitter", "lizard", "grimp + import-linter", "NetworkX"]}
            artifact={
              <TerminalWindow title="mri scan . --verbose" meta="stage 1/5" tone="inset">
                <pre className={mono}>
                  <span className="text-mute"># history</span>{"\n"}
                  <span className="text-secondary">  4,812 commits · 38 authors · 2019→2026</span>{"\n"}
                  <span className="text-mute"># structure</span>{"\n"}
                  <span className="text-secondary">  270 files · 18,452 symbols · 6 languages</span>{"\n"}
                  <span className="text-mute"># measured</span>{"\n"}
                  <span className="text-secondary">  hotspots <span className="text-risk-high">12</span> · cycles <span className="text-risk-medium">3</span> · knowledge islands <span className="text-risk-critical">2</span></span>
                </pre>
              </TerminalWindow>
            }
          />

          {/* 02 — session logs: trace artifact */}
          <StageShell
            n="02"
            flip
            title="Session-log provenance"
            module="the session-log ingest layer"
            body={
              <>
                Then, who wrote it. MRI reads the session logs already on your
                machine — ~/.claude, ~/.cursor — and maps prompt → file →
                commit. No cloud calls, no reconstruction: it reads what exists,
                and says so.
              </>
            }
            oss={["Agent Trace / git-ai git-notes (consumed)"]}
            artifact={
              <TerminalWindow title="session → commit trace" meta="stage 2/5" tone="inset">
                <pre className={mono}>
                  <span className="text-author-ai">session 7f3a</span>
                  <span className="text-mute"> · claude code · 14:02</span>{"\n"}
                  <span className="text-mute">  prompt</span>{"  "}&quot;extract session handling…&quot;{"\n"}
                  <span className="text-mute">  files</span>{"   "}<span className="text-secondary">auth/session.py · auth/tokens.py</span>{"\n"}
                  <span className="text-mute">  commit</span>{"  "}<span className="text-accent">bd41f2</span>
                  <span className="text-secondary"> refactor: session service</span>{"\n"}
                  <span className="text-mute">  method</span>{"  "}<span className="text-secondary">blame × session-commit correlation</span>
                </pre>
              </TerminalWindow>
            }
          />

          {/* 03 — risk decomposition: split bar artifact */}
          <StageShell
            n="03"
            title="Authorship-decomposed risk"
            module="the risk-scoring engine"
            body={
              <>
                Every analyzer emits a 0–100 score with a ledger behind it.
                Then the risk itself is split: how much came from AI-authored
                lines, how much from human ones. Unattributed stays
                unattributed — it is never quietly counted as human.
              </>
            }
            artifact={
              <TerminalWindow title="mri fusion · services/auth/session.py" meta="stage 3/5" tone="inset" bodyClassName="flex flex-col gap-4 p-5">
                <div className="flex items-baseline justify-between">
                  <span className="text-mute font-mono text-mono-sm">risk score</span>
                  <span className="font-mono text-mono-lg font-semibold">
                    <span className="text-risk-high">72</span>
                    <span className="text-mute"> / 100</span>
                  </span>
                </div>
                <AuthorshipSplitBar shares={{ human: 52, ai: 41, unattributed: 7 }} />
                <p className="text-mute font-mono text-mono-sm">
                  → 61% of this file&apos;s risk sits in AI-authored lines.
                </p>
              </TerminalWindow>
            }
          />

          {/* 04 — decisions: confidence table artifact */}
          <StageShell
            n="04"
            flip
            title="Decision provenance"
            module="the decision tables"
            body={
              <>
                The &quot;why&quot; behind a change becomes a first-class record
                instead of lore in someone&apos;s head. Each mined decision
                carries a confidence score based on where it came from.
              </>
            }
            artifact={
              <TerminalWindow title="decision sources" meta="stage 4/5" tone="inset" bodyClassName="p-0">
                <table className="w-full border-collapse text-left">
                  <caption className="sr-only">Decision sources and their confidence</caption>
                  <tbody>
                    {[
                      ["ADR document", "0.95", "text-risk-low"],
                      ["Commit message with rationale", "0.60", "text-risk-medium"],
                      ["Bare subject line", "0.30", "text-mute"],
                    ].map(([src, conf, cls]) => (
                      <tr key={src} className="border-hairline border-b last:border-b-0">
                        <th scope="row" className="text-secondary px-5 py-3.5 font-body text-body-sm font-normal">
                          {src}
                        </th>
                        <td className={`px-5 py-3.5 text-right font-mono text-mono font-semibold ${cls}`}>
                          {conf}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TerminalWindow>
            }
          />

          {/* 05 — consequence: the strip itself */}
          <StageShell
            n="05"
            title="Consequence loop"
            module="the consequence tables"
            body={
              <>
                Did it help? MRI links a decision to the metric that moved
                after it — 30-day window, confidence capped at 0.6, confounder
                guardrails. Always drawn as a dashed line, because it is a
                correlation, never a proof of cause.
              </>
            }
            artifact={
              <DecisionConsequenceStrip
                decision="Extracted the session service out of the auth monolith."
                consequence="Coupling on that path fell over the following 30 days."
                direction="improved"
                confidence="MED"
              />
            }
          />

          <div className="border-hairline flex flex-wrap gap-3 border-t pt-10">
            <ButtonLink href="/docs/session-log-setup">
              Point MRI at your session logs
              <ArrowRightIcon width={16} height={16} />
            </ButtonLink>
            <ButtonLink href={SITE.github} variant="secondary">
              Read the methodology
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
