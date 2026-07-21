import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section, SectionHeader } from "@/components/ui/container";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { DecisionConsequenceStrip } from "@/components/viz/decision-consequence-strip";
import { SITE } from "@/lib/site";
import { ArrowRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "How MRI Works — Session Logs, Risk Scoring & Consequence Tracking",
  description:
    "The technical credibility page: what module does each of MRI's five stages, what open-source it builds on, and a real example — not a mockup. Reuse over reinvention, credited.",
  alternates: { canonical: "/how-it-works" },
};

const STAGES = [
  {
    n: "01",
    title: "History + structure",
    module: "backend/mri/analyzers/git_history.py · architecture.py",
    oss: ["PyDriller", "py-tree-sitter", "tree-sitter-language-pack", "lizard", "grimp + import-linter", "NetworkX"],
    body: "MRI parses the full commit history and a real tree-sitter AST — an image of the code as it actually is, not a diff-shape guess. Hotspots, churn, ownership, coupling and complexity come from real measurements: PyDriller mines history, tree-sitter parses structure, lizard measures complexity, grimp + import-linter map imports, NetworkX finds cycles.",
  },
  {
    n: "02",
    title: "Session-log provenance",
    module: "the session-log ingest layer",
    oss: ["Agent Trace / git-ai git-notes (consumed)"],
    body: "MRI reads the session logs already on your machine — ~/.claude and ~/.cursor — and maps prompt → file → commit. It correlates a session to the earliest commit at or after the files were touched. Where Agent Trace or git-ai have written provenance as git-notes, MRI consumes those too. It does not call any cloud API to reconstruct sessions that weren't logged: it reads what exists, and says so.",
  },
  {
    n: "03",
    title: "Authorship-decomposed risk",
    module: "the risk-scoring engine",
    oss: [],
    body: "Each analyzer emits a 0–100 score with a contributor ledger, combined as a weighted mean. Then risk is split into AI-authored vs human-authored shares using git blame × the session-commit correlation. Unattributed lines are reported as unattributed — never folded into 'human'. Provenance is never folded into the base risk score; it decomposes it.",
  },
  {
    n: "04",
    title: "Decision provenance",
    module: "the decision tables",
    oss: [],
    body: "A decision is a mined, structured rationale — from an ADR (confidence 0.95), a commit message with real reasoning (0.6), or a bare subject line (0.3). MRI records the decision and its confidence, so the 'why' behind a change is a first-class artifact rather than lore in someone's head.",
  },
  {
    n: "05",
    title: "Consequence loop",
    module: "the consequence tables",
    oss: [],
    body: "MRI correlates a decision to a later measured metric delta — bounded to a 30-day window, capped at 0.6 confidence, with confounder guardrails. It is stated as correlation, never causation. This is the single hardest-to-copy piece of the product, and the one where honesty about what a measured link can claim matters most.",
  },
] as const;

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader
        eyebrow="how it works"
        title="Convinced by the mechanism, not the marketing."
        lede="Five stages, each naming the module that does it and the open source it builds on. Reuse over reinvention is a credibility signal, not something to hide — every dependency below is named and credited."
      />

      <Section>
        <Container>
          <ol className="flex flex-col gap-4">
            {STAGES.map((s) => (
              <li key={s.n}>
                <Card className="md:p-8">
                  <div className="grid gap-6 md:grid-cols-[auto_1fr]">
                    <span className="text-accent font-mono text-mono-lg font-semibold">
                      {s.n}
                    </span>
                    <div>
                      <h2 className="text-[length:var(--text-h3)] font-semibold">
                        {s.title}
                      </h2>
                      <p className="text-mute mt-1 font-mono text-mono-sm">
                        {s.module}
                      </p>
                      <p className="text-secondary mt-3 font-body text-body-lg leading-relaxed">
                        {s.body}
                      </p>
                      {s.oss.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {s.oss.map((o) => (
                            <Badge key={o} tone="neutral">
                              {o}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ol>
        </Container>
      </Section>

      <Section>
        <Container narrow>
          <SectionHeader
            eyebrow="the decision → consequence loop, honestly"
            title="A dashed line, on purpose."
            lede="MRI links a decision to the metric that moved after it — and draws that link as a dashed line, everywhere, forever. The dash is the honesty: it is a correlation with confounder guardrails, not a proof of cause. It answers 'did this seem to help', not 'this caused that'."
          />
          <div className="mt-8">
            <DecisionConsequenceStrip
              decision="Extracted the session service out of the auth monolith."
              consequence="Coupling on that path fell over the following 30 days."
              direction="improved"
              confidence="MED"
            />
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
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
