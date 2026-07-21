import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { CodePanel, Prompt, Comment, Out } from "@/components/ui/code-panel";
import { RiskRing } from "@/components/viz/risk-ring";
import { AuthorshipSplitBar } from "@/components/viz/authorship-split-bar";
import { SessionTraceCard } from "@/components/viz/session-trace-card";
import { DecisionConsequenceStrip } from "@/components/viz/decision-consequence-strip";
import { SITE } from "@/lib/site";
import { GitHubIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Live Demo — See MRI's Core Loop",
  description:
    "See MRI's risk ring, authorship split, session trace, and decision-to-consequence loop on an example repository — clearly labeled, then run mri scan . on your own code.",
  alternates: { canonical: "/demo" },
};

// Annotation shown under each panel: what the self-hosted product also does that
// a static preview structurally can't (per DEMO-SITE-SPEC §5).
function HeldBack({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-mute mt-4 border-t border-[var(--color-hairline)] pt-3 font-mono text-mono-sm">
      In your self-hosted instance → {children}
    </p>
  );
}

export default function DemoPage() {
  return (
    <>
      <PageHeader
        eyebrow="live demo"
        title="See the core loop in under two minutes."
        lede="A limited preview. Every panel below uses an illustrative example — labeled as such, never presented as real when it isn't. The full picture comes from running mri scan . on your own repository."
      />

      <Section>
        <Container>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <Badge tone="accent">Limited preview</Badge>
            <Badge tone="neutral">Illustrative data · labeled</Badge>
            <span className="text-mute font-mono text-mono-sm">
              example-org/service · representative repository
            </span>
          </div>

          <div className="grid gap-5 lg:grid-cols-12">
            {/* Risk overview — wide */}
            <Card className="lg:col-span-7">
              <div className="flex flex-col items-start gap-6 sm:flex-row sm:items-center">
                <RiskRing value={60} size={112} />
                <div>
                  <h2 className="font-sans text-body font-semibold">
                    Repository risk score
                  </h2>
                  <p className="text-secondary mt-2 font-body text-body-sm leading-relaxed">
                    A composite of six analyzers — git history, complexity, tech
                    debt, coupling, architecture, dependencies — each with a
                    contributor ledger. Unmeasured analyzers are excluded, never
                    zeroed.
                  </p>
                </div>
              </div>
              <HeldBack>the full history depth, every file, and each score&apos;s exact evidence.</HeldBack>
            </Card>

            {/* Authorship — narrow tall */}
            <Card className="lg:col-span-5">
              <h2 className="font-sans text-body font-semibold">
                Authorship share
              </h2>
              <p className="text-mute mt-1 font-mono text-mono-sm">
                services/auth/session.py
              </p>
              <div className="mt-4">
                <AuthorshipSplitBar shares={{ human: 52, ai: 41, unattributed: 7 }} />
              </div>
              <HeldBack>attribution from your real ~/.claude and ~/.cursor logs.</HeldBack>
            </Card>

            {/* Session trace */}
            <div className="lg:col-span-5">
              <SessionTraceCard
                source="CLAUDE CODE"
                when="illustrative"
                prompt="Refactor the auth module: pull session handling into its own service and add token rotation."
                files={[
                  { path: "services/auth/session.py", tier: "high" },
                  { path: "services/auth/tokens.py", tier: "medium" },
                  { path: "tests/test_session.py", tier: "low" },
                ]}
              />
              <p className="text-mute mt-3 font-mono text-mono-sm">
                Prompt excerpt is illustrative — real traces map to your own
                sessions.
              </p>
            </div>

            {/* Decision consequence — wide */}
            <div className="lg:col-span-7">
              <DecisionConsequenceStrip
                decision="Extracted the session service out of the auth monolith."
                consequence="Coupling on that path fell over the following 30 days."
                direction="improved"
                confidence="MED"
              />
              <p className="text-mute mt-3 font-mono text-mono-sm">
                Correlational, guardrailed, capped at 0.6 confidence — never a
                causal claim.
              </p>
            </div>
          </div>
        </Container>
      </Section>

      {/* Run it yourself */}
      <Section>
        <Container>
          <Card className="bg-raised md:p-9">
            <div className="grid items-center gap-8 md:grid-cols-[1fr_1fr]">
              <div>
                <h2 className="text-[length:var(--text-h3)] font-semibold text-balance">
                  This is a preview. The real picture is one command away.
                </h2>
                <p className="text-secondary mt-3 font-body text-body-lg leading-relaxed">
                  Nothing here is paywalled — MIT-forever means the full
                  capability is a <span className="text-accent">pip install</span>{" "}
                  away, on your machine, against your own code.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  <ButtonLink href="/docs/quickstart">Quickstart</ButtonLink>
                  <ButtonLink href={SITE.github} variant="secondary">
                    <GitHubIcon width={16} height={16} />
                    View on GitHub
                  </ButtonLink>
                </div>
              </div>
              <CodePanel title="your terminal" copyText={`pip install ${SITE.pkg}\nmri scan .`}>
                <Comment># install and scan your own repo</Comment>
                {"\n"}
                <Prompt />pip install {SITE.pkg}
                {"\n"}
                <Prompt />mri scan .{"\n\n"}
                <Out>✓ report at ~/.cache/project-mri/reports/…html</Out>
              </CodePanel>
            </div>
          </Card>
        </Container>
      </Section>
    </>
  );
}
