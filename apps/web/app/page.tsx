import { Link } from "@/components/link";
import { SITE } from "@/lib/site";
import { Container, Section, SectionHeader, Eyebrow } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CodePanel, Prompt, Comment, Out } from "@/components/ui/code-panel";
import { GridField } from "@/components/grid-field";
import { HomeJsonLd } from "@/components/json-ld";
import { AuthorshipSplitBar } from "@/components/viz/authorship-split-bar";
import { DecisionConsequenceStrip } from "@/components/viz/decision-consequence-strip";
import { ArrowRightIcon, ArrowUpRightIcon, GitHubIcon } from "@/components/icons";

const STAGES = [
  {
    n: "01",
    title: "History + structure",
    body: "Full git history and a real tree-sitter AST — an image of the code, not a guess.",
  },
  {
    n: "02",
    title: "Session-log provenance",
    body: "Reads local ~/.claude and ~/.cursor logs to map prompt → file → commit.",
  },
  {
    n: "03",
    title: "Authorship-decomposed risk",
    body: "Splits each file's risk into AI-authored vs human-authored shares.",
  },
  {
    n: "04",
    title: "Decision provenance",
    body: "Mines the rationale behind a change from ADRs and commit messages.",
  },
  {
    n: "05",
    title: "Consequence loop",
    body: "Correlates a decision to the metric that moved later — guardrailed, never causal.",
  },
] as const;

const EVIDENCE = [
  {
    stat: "Comprehension debt",
    body: "Code that ships and runs but that no one on the team understands well enough to safely change.",
    source: "Term coined by Addy Osmani",
    href: "https://addyo.substack.com/",
  },
  {
    stat: "~13,000 lines",
    body: "An AI-authored pull request the OCaml compiler community declined — over reviewability and provenance, not correctness.",
    source: "OCaml compiler discussion",
    href: "https://github.com/ocaml/ocaml",
  },
  {
    stat: "~81% more",
    body: "Production issues reported by teams shipping opaque-provenance AI-authored code.",
    source: "CloudBees, 2026",
    href: "https://www.cloudbees.com/",
  },
] as const;

export default function HomePage() {
  return (
    <>
      <HomeJsonLd />
      <GridField />

      {/* ---- Hero ---- */}
      <Section className="pt-14 pb-10 md:pt-20 md:pb-16">
        <Container>
          <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="accent">Local-first</Badge>
                <Badge tone="neutral">MIT-forever</Badge>
                <Badge tone="neutral">v{SITE.version}</Badge>
              </div>
              <h1 className="mt-5 text-[length:var(--text-display)] leading-[var(--text-display--line-height)] font-semibold text-balance">
                MRI reads what&apos;s actually in your codebase — and{" "}
                <span className="text-accent">who actually wrote it</span>.
              </h1>
              <p className="text-secondary mt-6 max-w-[54ch] font-body text-body-lg">
                Session-log AI provenance, authorship-decomposed risk, and a
                decision-to-consequence loop — all on your machine, all
                explainable, all MIT-forever.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <ButtonLink href="/demo" size="lg">
                  Try the live demo
                  <ArrowRightIcon width={18} height={18} />
                </ButtonLink>
                <ButtonLink href={SITE.github} variant="secondary" size="lg">
                  <GitHubIcon width={18} height={18} />
                  View on GitHub
                </ButtonLink>
              </div>
              <p className="text-mute mt-5 font-mono text-mono-sm">
                <span className="text-accent">$</span> pip install {SITE.pkg}
              </p>
            </div>

            <CodePanel
              title="mri scan ."
              meta="project-mri · own repo"
              copyText="mri scan ."
              className="shadow-[var(--elevation-2)]"
            >
              <Prompt />mri scan .{"\n\n"}
              <Comment># git history</Comment>
              {"\n"}  parsed 4,812 commits · 38 authors{"\n"}
              <Comment># tree-sitter</Comment>
              {"\n"}  270 files · 6 languages · 18,452 symbols{"\n"}
              <Comment># session logs</Comment>
              {"\n"}  ~/.claude · mapped prompts → files → commits{"\n"}
              <Comment># risk score</Comment>
              {"\n"}  <span className="text-risk-high">60.0</span> / 100 · measured{"\n"}
              <Comment># report</Comment>
              {"\n"}  ~/.cache/project-mri/reports/…html{"\n\n"}
              <Out>✓ done in 2.5s · 0 telemetry events</Out>
            </CodePanel>
          </div>
        </Container>
      </Section>

      {/* ---- Problem, with evidence ---- */}
      <Section>
        <Container>
          <SectionHeader
            eyebrow="the problem"
            title="Teams are shipping code they can't explain."
            lede="The demand is real and named — and it is not 'a nicer git blame'. It is: give me back the ability to trust code I didn't write and can't fully read, and show me your work."
          />
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {EVIDENCE.map((e) => (
              <Card key={e.stat}>
                <p className="text-accent font-sans text-h3 font-semibold">
                  {e.stat}
                </p>
                <p className="text-secondary mt-3 font-body text-body-sm leading-relaxed">
                  {e.body}
                </p>
                <a
                  href={e.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-mute hover:text-primary mt-4 inline-flex items-center gap-1 font-mono text-mono-sm transition-colors"
                >
                  {e.source}
                  <ArrowUpRightIcon width={13} height={13} />
                </a>
              </Card>
            ))}
          </div>
        </Container>
      </Section>

      {/* ---- Five-stage loop ---- */}
      <Section>
        <Container>
          <SectionHeader
            eyebrow="what closes the loop"
            title="Five stages, one complete loop."
            lede="Individually, most of these have a rival. Together — as a complete, trustworthy, free, self-hostable loop — MRI stands alone."
          />
          <ol className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {STAGES.map((s) => (
              <li key={s.n}>
                <Link
                  href="/how-it-works"
                  className="group border-hairline bg-surface hover:border-hairline-strong block h-full rounded-md border p-5 transition-colors"
                >
                  <span className="text-accent font-mono text-mono-sm font-medium">
                    {s.n}
                  </span>
                  <h3 className="mt-2 font-sans text-body font-semibold">
                    {s.title}
                  </h3>
                  <p className="text-secondary mt-2 font-body text-body-sm leading-relaxed">
                    {s.body}
                  </p>
                </Link>
              </li>
            ))}
          </ol>
          <p className="text-mute mt-6 font-mono text-mono-sm">
            → surfaced to humans (dashboard · HTML report · CLI · SARIF gate) and
            agents (MCP server).
          </p>
        </Container>
      </Section>

      {/* ---- Demo teaser ---- */}
      <Section>
        <Container>
          <div className="grid items-start gap-10 lg:grid-cols-2">
            <div>
              <Eyebrow>see it work</Eyebrow>
              <h2 className="mt-3 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                Authorship-decomposed risk, and a decision you can trace.
              </h2>
              <p className="text-secondary mt-4 max-w-[54ch] font-body text-body-lg">
                Every panel links to the exact commit, line, or AST node behind
                it. Nothing here asks for trust — only inspection.
              </p>
              <div className="mt-6">
                <ButtonLink href="/demo" variant="secondary">
                  Explore the live demo
                  <ArrowRightIcon width={16} height={16} />
                </ButtonLink>
              </div>
            </div>
            <div className="flex flex-col gap-5">
              <Card>
                <p className="text-mute font-mono text-mono-sm">
                  services/auth/session.py
                </p>
                <p className="text-secondary mt-3 mb-2 font-body text-body-sm">
                  Authorship share
                </p>
                <AuthorshipSplitBar
                  shares={{ human: 52, ai: 41, unattributed: 7 }}
                />
              </Card>
              <DecisionConsequenceStrip
                decision="Split the monolith auth module into a session service."
                consequence="Coupling on that path fell over the next 30 days."
                direction="improved"
                confidence="MED"
              />
            </div>
          </div>
          <p className="text-mute mt-4 font-mono text-mono-sm">
            Illustrative example — labeled, never presented as real when it
            isn&apos;t. Run <span className="text-accent">mri scan .</span> on your
            own code for the real picture.
          </p>
        </Container>
      </Section>

      {/* ---- Open source, forever ---- */}
      <Section>
        <Container>
          <Card className="bg-raised md:p-10">
            <div className="grid items-center gap-8 md:grid-cols-[1.3fr_1fr]">
              <div>
                <Eyebrow>open source, forever</Eyebrow>
                <h2 className="mt-3 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                  A tool that reads your prompts must be inspectable — and
                  un-revocable.
                </h2>
                <p className="text-secondary mt-4 max-w-[54ch] font-body text-body-lg">
                  MIT-licensed on the whole core, forever. Zero telemetry, proven
                  by a build-failing egress test. Fully self-hostable. Nothing
                  held back behind a paywall — because there is no paywall.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  <ButtonLink href={SITE.license}>
                    Read the license
                    <ArrowUpRightIcon width={16} height={16} />
                  </ButtonLink>
                  <ButtonLink href="/manifesto" variant="ghost">
                    The manifesto
                    <ArrowRightIcon width={16} height={16} />
                  </ButtonLink>
                </div>
              </div>
              <ul className="flex flex-col gap-3">
                {[
                  "MIT-forever — no open-core split, no paid tier",
                  "Zero telemetry — no account, no phone-home",
                  "Self-hostable — your code never leaves your machine",
                  "Explainable — every score traces to its evidence",
                ].map((line) => (
                  <li
                    key={line}
                    className="text-secondary border-hairline bg-surface flex items-start gap-3 rounded-md border p-3 font-body text-body-sm"
                  >
                    <span className="text-accent mt-0.5 font-mono">✓</span>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </Container>
      </Section>
    </>
  );
}
